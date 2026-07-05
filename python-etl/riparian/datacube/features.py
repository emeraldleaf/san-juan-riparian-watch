"""Feature builder for riparian delineation (Stage 1b).

Turns a Sentinel-2 (+ optional Sentinel-1) datacube into a per-pixel feature
matrix for the delineation models. Features follow the applied riparian RS
literature (Pace et al. 2022; USACE/ERDC review):

- **Spectral indices** per timestep: NDVI, EVI, NDMI (SWIR moisture), NDRE
  (red-edge), kNDVI — greenness, water stress, and chlorophyll without NDVI's
  saturation.
- **Multitemporal statistics** per index: median, p10, p90, and amplitude
  (p90 − p10) over the season/time window. Amplitude + dry-season persistence
  are the phreatophyte discriminators.
- **Texture** on the median NDVI: local standard deviation and local range —
  cheap proxies for the GLCM texture the literature uses, computed with
  scipy.ndimage (CPU-friendly; true GLCM is a documented future enhancement).

Terrain features (HAND, slope, distance-to-channel) are assembled separately
(they need the 3DEP DEM + stream network, not the optical cube) — see the
`terrain_features` extension point below.

Spatial dims are read via ``stac_datacube.spatial_dims`` (geographic cubes name
them latitude/longitude). See docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import xarray as xr
from scipy import ndimage

from riparian.datacube.stac import spatial_dims

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sentinel-2 L2A DN → reflectance. PC S2 uses scale 1e-4. The processing-
# baseline 04.00+ BOA offset (−0.1) is intentionally ignored: it cancels in the
# ratio indices and only slightly biases EVI, which is acceptable for a
# weak-label baseline. Documented caveat, not an oversight.
S2_REFLECTANCE_SCALE = 1e-4

# Texture window (pixels) for local std/range on the median NDVI.
TEXTURE_WINDOW = 3


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureStack:
    """Per-pixel feature matrix plus the grid needed to map results back.

    Attributes:
        data: ``(n_valid_pixels, n_features)`` float32 matrix.
        feature_names: Column names, aligned with ``data``'s second axis.
        valid_mask: ``(height, width)`` bool array — True where a pixel has
            complete features. Rows of ``data`` are the True cells in row-major
            order.
        y_coords: 1-D array of the y/latitude coordinate values (length height).
        x_coords: 1-D array of the x/longitude coordinate values (length width).
    """

    data: np.ndarray
    feature_names: tuple[str, ...]
    valid_mask: np.ndarray
    y_coords: np.ndarray
    x_coords: np.ndarray


# ---------------------------------------------------------------------------
# Pure index functions (operate on xarray DataArrays or numpy arrays)
# ---------------------------------------------------------------------------


def _safe_ratio(numerator: xr.DataArray, denominator: xr.DataArray) -> xr.DataArray:
    """Normalized-difference-style ratio with divide-by-zero → NaN."""
    return numerator / denominator.where(denominator != 0)


def ndvi(nir: xr.DataArray, red: xr.DataArray) -> xr.DataArray:
    """NDVI = (NIR − Red) / (NIR + Red). Greenness / density."""
    return _safe_ratio(nir - red, nir + red)


def ndmi(nir: xr.DataArray, swir1: xr.DataArray) -> xr.DataArray:
    """NDMI = (NIR − SWIR1) / (NIR + SWIR1). Canopy water / moisture stress."""
    return _safe_ratio(nir - swir1, nir + swir1)


def ndre(nir: xr.DataArray, rededge: xr.DataArray) -> xr.DataArray:
    """NDRE = (NIR − RedEdge) / (NIR + RedEdge). Chlorophyll, less saturating."""
    return _safe_ratio(nir - rededge, nir + rededge)


def evi(nir: xr.DataArray, red: xr.DataArray, blue: xr.DataArray) -> xr.DataArray:
    """EVI = 2.5·(NIR − Red) / (NIR + 6·Red − 7.5·Blue + 1). Needs reflectance."""
    denom = nir + 6.0 * red - 7.5 * blue + 1.0
    return 2.5 * _safe_ratio(nir - red, denom)


def kndvi(nir: xr.DataArray, red: xr.DataArray) -> xr.DataArray:
    """kNDVI = tanh(NDVI²). Kernel NDVI — robust to saturation."""
    nd = ndvi(nir, red)
    return np.tanh(nd**2)


# ---------------------------------------------------------------------------
# Index cube assembly
# ---------------------------------------------------------------------------


def compute_index_cube(cube: xr.Dataset) -> xr.Dataset:
    """Compute a per-timestep index cube from a Sentinel-2 reflectance cube.

    Scales DN → reflectance, then computes NDVI, EVI, NDMI, NDRE, kNDVI for
    every timestep.

    Args:
        cube: Sentinel-2 dataset with variables B02, B04, B05, B08, B11 (at
            least). Extra bands are ignored.

    Returns:
        An xarray Dataset with variables ``ndvi``/``evi``/``ndmi``/``ndre``/
        ``kndvi`` over the same ``(time, y, x)`` dims.
    """
    r = cube.astype("float32") * S2_REFLECTANCE_SCALE
    blue, red, rededge = r["B02"], r["B04"], r["B05"]
    nir, swir1 = r["B08"], r["B11"]
    return xr.Dataset(
        {
            "ndvi": ndvi(nir, red),
            "evi": evi(nir, red, blue),
            "ndmi": ndmi(nir, swir1),
            "ndre": ndre(nir, rededge),
            "kndvi": kndvi(nir, red),
        }
    )


def temporal_stats(index_cube: xr.Dataset) -> xr.Dataset:
    """Reduce a per-timestep index cube to multitemporal statistics.

    For each index computes median, p10, p90, and amplitude (p90 − p10) across
    time, ignoring NaNs (cloud-masked pixels). Amplitude captures phenological
    range; p10 captures dry-season floor (groundwater subsidy persistence).

    Args:
        index_cube: Output of :func:`compute_index_cube`.

    Returns:
        A Dataset with one variable per ``<index>_<stat>`` over ``(y, x)``.
    """
    out: dict[str, xr.DataArray] = {}
    for name, da in index_cube.data_vars.items():
        median = da.median(dim="time", skipna=True)
        p10 = da.quantile(0.10, dim="time", skipna=True).drop_vars("quantile")
        p90 = da.quantile(0.90, dim="time", skipna=True).drop_vars("quantile")
        out[f"{name}_median"] = median
        out[f"{name}_p10"] = p10
        out[f"{name}_p90"] = p90
        out[f"{name}_amplitude"] = p90 - p10
    return xr.Dataset(out)


# ---------------------------------------------------------------------------
# Texture (pure numpy / scipy)
# ---------------------------------------------------------------------------


def local_texture(arr: np.ndarray, window: int = TEXTURE_WINDOW) -> dict[str, np.ndarray]:
    """Local texture features via a moving window (NaN-aware).

    Computes local standard deviation and local range (max − min) over a
    ``window×window`` neighbourhood — cheap CPU-friendly proxies for GLCM
    texture. NaNs are filled with the nanmean before filtering so edges/gaps
    don't propagate, then re-masked.

    Args:
        arr: 2-D array (e.g. median NDVI).
        window: Neighbourhood size in pixels.

    Returns:
        Dict with ``texture_std`` and ``texture_range`` 2-D arrays.
    """
    nan_mask = ~np.isfinite(arr)
    filled = np.where(nan_mask, np.nanmean(arr), arr).astype("float32")

    mean = ndimage.uniform_filter(filled, size=window, mode="nearest")
    mean_sq = ndimage.uniform_filter(filled**2, size=window, mode="nearest")
    variance = np.clip(mean_sq - mean**2, 0.0, None)
    std = np.sqrt(variance)

    local_max = ndimage.maximum_filter(filled, size=window, mode="nearest")
    local_min = ndimage.minimum_filter(filled, size=window, mode="nearest")
    rng = local_max - local_min

    std[nan_mask] = np.nan
    rng[nan_mask] = np.nan
    return {"texture_std": std, "texture_range": rng}


# ---------------------------------------------------------------------------
# Feature-stack assembly
# ---------------------------------------------------------------------------


def build_feature_stack(cube: xr.Dataset) -> FeatureStack:
    """Build the per-pixel feature matrix from a Sentinel-2 cube.

    Combines multitemporal index statistics + texture on median NDVI into a
    ``(n_valid_pixels, n_features)`` matrix. A pixel is valid only if every
    feature is finite (fully cloud-free enough to have a season median).

    Args:
        cube: Sentinel-2 datacube from ``stac_datacube.build_sentinel2_cube``.

    Returns:
        A :class:`FeatureStack`.
    """
    y_dim, x_dim = spatial_dims(cube)
    # Load the index cube into memory before reducing: numpy-backed quantile is
    # fast, whereas dask's lazy quantile rechunks the whole time axis and is the
    # dominant cost on a small AOI.
    index_cube = compute_index_cube(cube).compute()
    stats = temporal_stats(index_cube)

    # Stack the 2-D stat layers into (features, y, x), preserving order.
    feature_names: list[str] = list(stats.data_vars)
    layers = [stats[name].values for name in feature_names]

    tex = local_texture(stats["ndvi_median"].values)
    for tex_name, tex_arr in tex.items():
        feature_names.append(tex_name)
        layers.append(tex_arr)

    stack = np.stack(layers, axis=0).astype("float32")  # (features, y, x)
    n_features, height, width = stack.shape

    flat = stack.reshape(n_features, height * width).T  # (pixels, features)
    valid = np.isfinite(flat).all(axis=1)
    valid_mask = valid.reshape(height, width)

    logger.info(
        "Feature stack: %d features, %d/%d valid pixels (%.0f%%)",
        n_features, int(valid.sum()), valid.size,
        100.0 * valid.sum() / max(valid.size, 1),
    )
    return FeatureStack(
        data=flat[valid],
        feature_names=tuple(feature_names),
        valid_mask=valid_mask,
        y_coords=cube[y_dim].values,
        x_coords=cube[x_dim].values,
    )
