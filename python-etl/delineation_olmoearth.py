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
from dataclasses import dataclass

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

from stac_datacube import spatial_dims

logger = logging.getLogger(__name__)

# OlmoEarth's Sentinel-2 L2A band order (fixed by the model).
OLMOEARTH_S2_ORDER = list(Modality.SENTINEL2_L2A.band_order)
DEFAULT_PATCH_SIZE = 8
S2_SCALE = 1e-4  # DN → reflectance


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
    # NOTE (finish on GPU VM): the encoder tokenizes S2 into
    # P_H × P_W × T × band_sets tokens (band_sets = 3, at resolution factors
    # 16/32/64), so the token count for a 112px/patch8/T8 AOI is 14·14·8·3 = 4704.
    # A pixel-resolution (1,H,W,T) mask collapses to 588 and mismatches. The
    # correct token-mask shape/convention (per-band-set, matching flexi_vit's
    # tokenizer) is the one remaining piece to verify the encoder end-to-end.
    valid = np.isfinite(s2).all(axis=-1)           # (1, H, W, T)
    mask = np.where(valid, MaskValue.ONLINE_ENCODER.value, MaskValue.MISSING.value)

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
