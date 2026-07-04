"""HAND (Height Above Nearest Drainage) envelope — Stage 1A.

Computes a physically-derived *candidate riparian corridor* from the 3DEP DEM:
low HAND = hydrologically connected valley bottom where riparian vegetation can
exist. This replaces the fixed hydrology buffer as the container that constrains
Stage-1B EO delineation — it eliminates uplands early, cutting false positives
and compute.

Flow routing uses pysheds. The DEM is loaded onto the Sentinel-2 grid (via
``like=cube``) so HAND aligns 1:1 with the feature stack. HAND can also be used
as a per-pixel feature, not just a mask.

Caveat: HAND is computed within the tile grid, so drainage entering from outside
the tile is truncated → edge cells are approximate. For a per-HUC12 candidate
envelope this is acceptable; a buffered-DEM variant is a future refinement.

See docs/specs/2026-07-03-stage1-riparian-delineation.md (Stage 1A).
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass

import numpy as np
import rasterio
import xarray as xr
from odc.stac import stac_load

from stac_datacube import STORAGE_CRS, StacSearcher, spatial_dims

logger = logging.getLogger(__name__)

# DEM sources tried in order. Copernicus GLO-30 is a clean single-resolution
# global DEM (robust); 3dep-seamless is a US multi-resolution mosaic that can
# return all-nodata for some tiles (e.g. steep CO headwaters) — kept as fallback.
DEM_COLLECTIONS = ("cop-dem-glo-30", "3dep-seamless")
MIN_DEM_FINITE_FRAC = 0.5        # reject a DEM that is mostly nodata
DEFAULT_ACC_THRESHOLD = 100      # flow-accumulation cells to seed the drainage network
DEFAULT_HAND_THRESHOLD_M = 8.0   # HAND <= this (metres) = candidate riparian corridor


@dataclass(frozen=True)
class HandResult:
    """HAND grid + derived candidate-corridor envelope.

    Attributes:
        hand: ``(y, x)`` float32 HAND in metres (NaN where undefined).
        envelope: ``(y, x)`` bool — HAND <= threshold (candidate corridor).
        y_coords: latitude coordinate values.
        x_coords: longitude coordinate values.
    """

    hand: np.ndarray
    envelope: np.ndarray
    y_coords: np.ndarray
    x_coords: np.ndarray


def load_dem_grid(
    bbox: tuple[float, float, float, float],
    searcher: StacSearcher,
    like: xr.Dataset,
) -> xr.DataArray | None:
    """Load the 3DEP seamless DEM onto the reference (S2) grid.

    Args:
        bbox: AOI ``(minx, miny, maxx, maxy)`` in EPSG:4269.
        searcher: STAC searcher.
        like: Reference cube whose geobox the DEM is aligned to.

    Returns:
        A 2-D DEM DataArray on the reference grid, or None if unavailable.
    """
    for collection in DEM_COLLECTIONS:
        items = searcher.search(collection, bbox, "1900-01-01/2100-01-01", None)
        if not items:
            continue
        dem = stac_load(
            items, bands=["data"], like=like, chunks={}, resampling="bilinear",
        )["data"]
        if "time" in dem.dims:
            dem = dem.isel(time=0, drop=True)
        dem = dem.compute()
        finite = float(np.isfinite(dem.values).mean())
        if finite >= MIN_DEM_FINITE_FRAC:
            logger.info("DEM from %s: %.0f%% finite", collection, 100 * finite)
            return dem
        logger.warning(
            "DEM from %s only %.0f%% finite for %s — trying next source",
            collection, 100 * finite, bbox,
        )
    logger.warning("No usable DEM for bbox %s", bbox)
    return None


def compute_hand(
    dem: xr.DataArray,
    *,
    acc_threshold: int = DEFAULT_ACC_THRESHOLD,
    hand_threshold_m: float = DEFAULT_HAND_THRESHOLD_M,
) -> HandResult:
    """Compute HAND + the candidate-corridor envelope from a gridded DEM.

    Conditions the DEM (fill pits → fill depressions → resolve flats), derives
    flow direction + accumulation, seeds a drainage network at
    ``acc_threshold`` cells, and computes HAND relative to it.

    Args:
        dem: 2-D DEM DataArray on the target grid (EPSG:4269).
        acc_threshold: Flow-accumulation cells to define the drainage network.
        hand_threshold_m: HAND cutoff for the candidate corridor.

    Returns:
        A :class:`HandResult`.
    """
    from pysheds.grid import Grid  # imported lazily (heavy, optional dep)

    y_dim, x_dim = spatial_dims(dem)
    arr = np.asarray(dem.values, dtype=np.float32)
    transform = dem.odc.geobox.affine

    # pysheds reads from a raster; write the gridded DEM to a temp GeoTIFF.
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=True) as tmp:
        profile = {
            "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1],
            "count": 1, "dtype": "float32", "crs": STORAGE_CRS,
            "transform": transform, "nodata": np.nan,
        }
        with rasterio.open(tmp.name, "w", **profile) as dst:
            dst.write(arr, 1)

        grid = Grid.from_raster(tmp.name)
        dem_r = grid.read_raster(tmp.name)
        conditioned = grid.resolve_flats(
            grid.fill_depressions(grid.fill_pits(dem_r))
        )
        fdir = grid.flowdir(conditioned)
        acc = grid.accumulation(fdir)
        hand_r = grid.compute_hand(fdir, conditioned, acc > acc_threshold)

    hand = np.asarray(hand_r, dtype=np.float32)
    envelope = np.isfinite(hand) & (hand <= hand_threshold_m)
    logger.info(
        "HAND envelope: %d/%d cells within %.0f m of drainage (%.1f%%)",
        int(envelope.sum()), envelope.size, hand_threshold_m,
        100.0 * envelope.sum() / max(envelope.size, 1),
    )
    return HandResult(
        hand=hand, envelope=envelope,
        y_coords=dem[y_dim].values, x_coords=dem[x_dim].values,
    )


def build_hand_envelope(
    bbox: tuple[float, float, float, float],
    searcher: StacSearcher,
    like: xr.Dataset,
    *,
    acc_threshold: int = DEFAULT_ACC_THRESHOLD,
    hand_threshold_m: float = DEFAULT_HAND_THRESHOLD_M,
) -> HandResult | None:
    """Load the DEM and compute the HAND candidate-corridor envelope.

    Returns None if the DEM is unavailable (the caller should then fall back to
    delineating the whole grid).
    """
    dem = load_dem_grid(bbox, searcher, like)
    if dem is None:
        return None
    return compute_hand(
        dem, acc_threshold=acc_threshold, hand_threshold_m=hand_threshold_m,
    )
