"""OlmoEarth foundation-model delineation (Stage 1b, cutting-edge track).

Extracts OlmoEarth multimodal embeddings from the Sentinel-2 datacube and uses
them as features for riparian delineation — the learned-representation contender
to the RandomForest baseline. Same weak labels + spatial-CV harness, so the two
can be compared head-to-head (baseline vs FM, with disagreement maps).

Runs on CPU with the Nano model for small AOIs; the basin-scale "OlmoEarth
everywhere" run is GPU (Hyperstack). Persist embeddings so classifiers re-run
without re-encoding. See
docs/specs/2026-07-03-stage1-riparian-delineation.md (OlmoEarth track).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np
import torch
import xarray as xr

from olmoearth_pretrain_minimal import ModelID, Normalizer, load_model_from_id
from olmoearth_pretrain_minimal.olmoearth_pretrain_v1.nn.latent_mim import (
    unpack_encoder_output,
)
from olmoearth_pretrain_minimal.olmoearth_pretrain_v1.utils.constants import Modality
from olmoearth_pretrain_minimal.olmoearth_pretrain_v1.utils.datatypes import (
    MaskValue,
    MaskedOlmoEarthSample,
)

from rasterio.transform import from_bounds

from riparian.datacube.features import build_feature_stack
from riparian.datacube.stac import (
    CubeRequest,
    PlanetaryComputerSearcher,
    StacSearcher,
    build_sentinel2_cube,
    spatial_dims,
)
from riparian.delineation.baseline import predict_proba, train
from riparian.delineation.runner import _cv_estimator, _vectorize, _write_extent
from riparian.delineation.validate import CvReport, assign_spatial_folds, spatial_cv
from riparian.validation.reference import fetch_nmripmap, rasterize_mask

logger = logging.getLogger(__name__)

# OlmoEarth's Sentinel-2 L2A band order (fixed by the model).
OLMOEARTH_S2_ORDER = list(Modality.SENTINEL2_L2A.band_order)
DEFAULT_PATCH_SIZE = 8
S2_SCALE = 1e-4  # DN → reflectance
# S2 L2A is tokenized in 3 band-sets (by native resolution); the token mask carries
# a trailing band-set axis (see build_sample). flexi_vit stacks per-band-set masks.
S2_NUM_BAND_SETS = 3


@dataclass(frozen=True)
class EmbeddingGrid:
    """Per-patch OlmoEarth embeddings over an AOI.

    Attributes:
        data: ``(P_H, P_W, D)`` float32 patch embeddings.
        patch_size: Patch size (pixels) used by the encoder.
        y_coords: latitude coordinate values of the source pixel grid.
        x_coords: longitude coordinate values of the source pixel grid.
    """

    data: np.ndarray
    patch_size: int
    y_coords: np.ndarray
    x_coords: np.ndarray


def load_olmoearth(
    model_id: ModelID = ModelID.OLMOEARTH_V1_NANO, *, weights: bool = True,
) -> torch.nn.Module:
    """Load an OlmoEarth encoder in eval mode (CPU-friendly for Nano)."""
    model = load_model_from_id(model_id, load_weights=weights)
    model.eval()
    return model


def _reorder_and_normalize(cube: xr.Dataset) -> np.ndarray:
    """Reorder the S2 cube to OlmoEarth band order and normalize.

    Returns:
        A ``(1, H, W, T, 12)`` float32 array (batch=1), normalized to ~[0, 1].
    """
    y_dim, x_dim = spatial_dims(cube)
    # (T, H, W) per band → stack in OlmoEarth order → (H, W, T, 12)
    bands = [cube[b] for b in OLMOEARTH_S2_ORDER]
    stack = np.stack([b.transpose("time", y_dim, x_dim).values for b in bands], axis=-1)
    stack = np.transpose(stack, (1, 2, 0, 3))  # (H, W, T, 12)
    reflectance = stack.astype("float32") * S2_SCALE
    normalized = Normalizer(std_multiplier=2.0).normalize(
        Modality.SENTINEL2_L2A, reflectance,
    )
    return normalized[np.newaxis, ...]  # (1, H, W, T, 12)


def build_sample(cube: xr.Dataset, bbox: tuple[float, float, float, float]) -> MaskedOlmoEarthSample:
    """Construct a MaskedOlmoEarthSample from the Sentinel-2 datacube.

    All present pixels are marked ONLINE_ENCODER (used for inference); non-finite
    (cloud-masked) pixels are MISSING. Timestamps are (day, month-1, year).

    Args:
        cube: Sentinel-2 datacube (12 reflectance bands + dropped SCL).
        bbox: AOI ``(minx, miny, maxx, maxy)`` for the latlon centroid.

    Returns:
        A MaskedOlmoEarthSample ready for ``model.encoder``.
    """
    s2 = _reorder_and_normalize(cube)              # (1, H, W, T, 12)
    s2 = np.nan_to_num(s2, nan=0.0)

    # Token mask, all ONLINE_ENCODER (present) for inference — no MAE removal.
    # flexi_vit tokenizes S2 per BAND-SET: for a spatial modality it reads the mask
    # as modality_mask[:, 0::stride, 0::stride, ..., idx] for idx in range(band_sets)
    # — so the mask needs a trailing band-set axis. A pixel-resolution (1,H,W,T) mask
    # has none and mismatches the token count. Give it (1,H,W,T,band_sets); the
    # encoder strides H/W down to patch resolution itself.
    valid = np.isfinite(s2).all(axis=-1)           # (1, H, W, T)
    mask_pix = np.where(valid, MaskValue.ONLINE_ENCODER.value, MaskValue.MISSING.value)
    mask = np.repeat(mask_pix[..., np.newaxis], S2_NUM_BAND_SETS, axis=-1)  # (1,H,W,T,B)

    # Timestamps (1, T, 3): day, month-1 (zero-indexed), year — integer (used as
    # nn.Embedding indices for the temporal encoding).
    times = cube["time"].values
    ts = np.array([[_ymd(t) for t in times]], dtype=np.int64)  # (1, T, 3)

    lat_c = (bbox[1] + bbox[3]) / 2.0
    lon_c = (bbox[0] + bbox[2]) / 2.0
    latlon = np.array([[lat_c, lon_c]], dtype=np.float32)          # (1, 2)
    latlon_mask = np.full((1, 2), MaskValue.ONLINE_ENCODER.value, dtype=np.float32)

    return MaskedOlmoEarthSample(
        timestamps=torch.from_numpy(ts),
        sentinel2_l2a=torch.from_numpy(s2.astype("float32")),
        sentinel2_l2a_mask=torch.from_numpy(mask.astype("int64")),
        latlon=torch.from_numpy(latlon),
        latlon_mask=torch.from_numpy(latlon_mask),
    )


def _ymd(t: np.datetime64) -> list[int]:
    """Extract [day, month-1, year] from a numpy datetime64 (integers)."""
    dt = np.datetime64(t, "D").astype("datetime64[D]").item()
    return [int(dt.day), int(dt.month - 1), int(dt.year)]


@torch.no_grad()
def extract_embeddings(
    model: torch.nn.Module, cube: xr.Dataset,
    bbox: tuple[float, float, float, float],
    *, patch_size: int = DEFAULT_PATCH_SIZE,
) -> EmbeddingGrid:
    """Run the OlmoEarth encoder and return per-patch embeddings.

    Args:
        model: A loaded OlmoEarth model (``load_olmoearth``).
        cube: Sentinel-2 datacube.
        bbox: AOI bbox (for latlon).
        patch_size: Encoder patch size.

    Returns:
        An :class:`EmbeddingGrid` with ``(P_H, P_W, D)`` patch embeddings.
    """
    y_dim, x_dim = spatial_dims(cube)
    sample = build_sample(cube, bbox)
    output_dict = model.encoder(sample, patch_size=patch_size)
    latent, _pooled, _kwargs = unpack_encoder_output(output_dict)

    # latent.sentinel2_l2a: (B, P_H, P_W, T, Band_Sets, D) → mean over T + Band_Sets
    tokens = latent.sentinel2_l2a
    emb = tokens.mean(dim=(3, 4)).squeeze(0)       # (P_H, P_W, D)
    emb_np = emb.detach().cpu().numpy().astype("float32")
    logger.info(
        "OlmoEarth embeddings: %s patches, D=%d (patch_size=%d)",
        emb_np.shape[:2], emb_np.shape[-1], patch_size,
    )
    return EmbeddingGrid(
        data=emb_np, patch_size=patch_size,
        y_coords=cube[y_dim].values, x_coords=cube[x_dim].values,
    )


# ---------------------------------------------------------------------------
# OlmoEarth delineation runner — the FM contender to the RF run_delineation.
# See docs/olmoearth-vs-rf-baseline.md for the head-to-head result + analysis.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OlmoEarthResult:
    """Outcome of an OlmoEarth delineation run."""

    method: str
    model_version: str
    n_patches: int
    n_polygons: int
    cv: CvReport


def _crop_to_square(cube: xr.Dataset, y_dim: str, x_dim: str, factor: int = 64):
    """Center-crop the cube to a square whose side is a multiple of ``factor``.

    OlmoEarth's 2D sincos position encoding is square, and its tokenizer needs the
    grid divisible by the band-set resolution factors (up to 64), so a non-square
    or oddly-sized AOI fails to encode. Returns ``(cube, side, bbox)``.
    """
    h, w = cube.sizes[y_dim], cube.sizes[x_dim]
    side = max(factor, (min(h, w) // factor) * factor)
    y0, x0 = (h - side) // 2, (w - side) // 2
    cube = cube.isel({y_dim: slice(y0, y0 + side), x_dim: slice(x0, x0 + side)})
    bbox = (float(cube[x_dim].min()), float(cube[y_dim].min()),
            float(cube[x_dim].max()), float(cube[y_dim].max()))
    return cube, side, bbox


def _aggregate_to_patches(
    pixel_mask: np.ndarray, valid_mask: np.ndarray, p_h: int, p_w: int, patch: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Majority-aggregate pixel bool grids to ``(p_h*p_w,)`` patch label + validity."""
    h, w = p_h * patch, p_w * patch
    lab = pixel_mask[:h, :w].reshape(p_h, patch, p_w, patch).mean(axis=(1, 3)) >= 0.5
    val = valid_mask[:h, :w].reshape(p_h, patch, p_w, patch).mean(axis=(1, 3)) >= 0.5
    return lab.astype(np.int64).reshape(-1), val.reshape(-1)


def run_delineation_olmoearth(
    bbox: tuple[float, float, float, float],
    engine,
    *,
    date_range: str,
    huc12: str | None = None,
    patch_size: int = DEFAULT_PATCH_SIZE,
    max_timesteps: int = 5,
    max_cloud_cover: int = 30,
    resolution_m: float = 10.0,
    probability_threshold: float = 0.5,
    searcher: StacSearcher | None = None,
) -> OlmoEarthResult:
    """Delineate riparian extent with OlmoEarth embeddings + a light RF head.

    The foundation-model contender to the RandomForest :func:`run_delineation`.
    Encodes the Sentinel-2 datacube into per-8x8-patch OlmoEarth embeddings, trains
    a light RF head on NMRipMap patch labels, spatial-cross-validates, and writes
    ``silver.riparian_extent`` with ``method='olmoearth'`` — so the two tracks can
    be diffed head-to-head on the same AOI.

    CPU/Nano needs a SMALL, square AOI + few timesteps (the encoder tokenizes to a
    square patch grid; the basin-scale "OlmoEarth everywhere" run is GPU). The AOI
    is center-cropped to a square and timesteps are subsampled to ``max_timesteps``.

    Raises:
        RuntimeError: no imagery, or NMRipMap labels are single-class over the AOI.
    """
    searcher = searcher or PlanetaryComputerSearcher()
    cube = build_sentinel2_cube(
        CubeRequest(bbox=bbox, date_range=date_range, resolution_m=resolution_m,
                    max_cloud_cover=max_cloud_cover),
        searcher,
    )
    if cube is None:
        raise RuntimeError(f"No Sentinel-2 imagery for {bbox} over {date_range}")
    step = max(1, cube.sizes["time"] // max_timesteps)
    cube = cube.isel(time=slice(None, None, step))
    y_dim, x_dim = spatial_dims(cube)
    cube, side, aoi = _crop_to_square(cube, y_dim, x_dim)
    logger.info("OlmoEarth AOI: %dx%d square, %d timesteps", side, side, cube.sizes["time"])

    features = build_feature_stack(cube)
    ref_mask = rasterize_mask(fetch_nmripmap(aoi), aoi, (side, side))
    if not 0 < int(ref_mask.sum()) < ref_mask.size:
        raise RuntimeError("NMRipMap labels single-class over AOI — pick a balanced AOI")

    emb = extract_embeddings(load_olmoearth(), cube, aoi, patch_size=patch_size)
    p_h, p_w, d = emb.data.shape
    x_patch = emb.data.reshape(p_h * p_w, d)
    y_patch, valid_patch = _aggregate_to_patches(
        ref_mask, features.valid_mask, p_h, p_w, patch_size)

    h, w = p_h * patch_size, p_w * patch_size
    yc = cube[y_dim].values[:h].reshape(p_h, patch_size).mean(1)
    xc = cube[x_dim].values[:w].reshape(p_w, patch_size).mean(1)
    yy, xx = np.meshgrid(yc, xc, indexing="ij")
    ll = np.column_stack([yy.reshape(-1), xx.reshape(-1)])

    xf, yf, llf = x_patch[valid_patch], y_patch[valid_patch], ll[valid_patch]
    names = tuple(f"oe_{i}" for i in range(d))
    head = replace(train(xf, yf, names, n_estimators=150, model_version="olmoearth-nano-v1"),
                   method="olmoearth")
    cv = spatial_cv(xf, yf, assign_spatial_folds(llf[:, 0], llf[:, 1], block_deg=0.004),
                    n_folds=4, estimator=_cv_estimator())
    logger.info("OlmoEarth spatial-CV: %s", cv.metrics)

    proba = predict_proba(head, x_patch).reshape(p_h, p_w)
    prob_grid = np.kron(proba, np.ones((patch_size, patch_size), np.float32))[:side, :side]
    riparian = (prob_grid >= probability_threshold) & features.valid_mask[:side, :side]
    transform = from_bounds(aoi[0], aoi[1], aoi[2], aoi[3], side, side)
    rows = _vectorize(riparian, prob_grid, transform, head, resolution_m, huc12)
    n_polygons = _write_extent(engine, rows, head, huc12)
    return OlmoEarthResult("olmoearth", head.model_version, int(valid_patch.sum()), n_polygons, cv)
