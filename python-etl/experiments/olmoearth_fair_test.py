"""Issue #9 — the fair RF-vs-OlmoEarth test.

Holds EVERYTHING constant except the representation:
  same AOI, same corrected NMRipMap labels, same patch grid, same spatial folds,
  same RandomForest head (_cv_estimator).

Arms:
  rf_features      — the 22 hand-crafted multitemporal features, patch-mean aggregated
  oe_mean_time     — OlmoEarth v1.1-Nano, mean-pooled over time  (the PUBLISHED harness)
  oe_temporal_stats— OlmoEarth v1.1-Nano, phenology-preserving pooling
  oe_concat_time   — OlmoEarth v1.1-Nano, full trajectory

If `oe_mean_time` is much worse than `oe_temporal_stats`, the published
"RF beats the foundation model" result was measuring our harness, not the model.
"""
from __future__ import annotations

import json
import logging
import sys
import time

import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from riparian.datacube.features import build_feature_stack          # noqa: E402
from riparian.datacube.stac import (                                # noqa: E402
    CubeRequest, PlanetaryComputerSearcher, build_sentinel2_cube, spatial_dims,
)
from riparian.delineation.olmoearth import (                        # noqa: E402
    DEFAULT_MODEL_ID, _aggregate_to_patches, _crop_to_square,
    extract_embeddings, load_olmoearth,
)
from riparian.delineation.runner import _cv_estimator               # noqa: E402
from riparian.delineation.validate import assign_spatial_folds, spatial_cv  # noqa: E402
from riparian.validation.reference import fetch_nmripmap, rasterize_mask    # noqa: E402

# Malpais tile (HUC12 140801051001) — a balanced lowland/alluvial sub-AOI.
# RECORDED here because the published run never wrote its bbox down.
BBOX = (-108.80, 36.86, -108.75, 36.90)
DATE_RANGE = "2024-04-01/2024-11-01"     # green-up -> senescence (phenology needs both)
MAX_TIMESTEPS = 12                        # monthly, matching Ai2's mangrove recipe
PATCH = 8
BLOCK_DEG = 0.004                         # ~400 m spatial blocks (held out whole)
N_FOLDS = 4


def patch_mean(pixel_feats: np.ndarray, valid: np.ndarray, p_h: int, p_w: int) -> np.ndarray:
    """Aggregate the per-pixel RF feature stack onto the SAME patch grid the encoder uses."""
    h, w = p_h * PATCH, p_w * PATCH
    n_f = pixel_feats.shape[1]
    dense = np.full((*valid.shape, n_f), np.nan, dtype="float32")
    dense[valid] = pixel_feats
    blocks = dense[:h, :w].reshape(p_h, PATCH, p_w, PATCH, n_f)
    with np.errstate(invalid="ignore"):
        out = np.nanmean(blocks, axis=(1, 3))          # (p_h, p_w, n_f)
    return np.nan_to_num(out).reshape(p_h * p_w, n_f)


def main() -> int:
    t0 = time.time()
    print(f"AOI {BBOX}  {DATE_RANGE}  model={DEFAULT_MODEL_ID.value}\n")

    cube = build_sentinel2_cube(
        CubeRequest(bbox=BBOX, date_range=DATE_RANGE, resolution_m=10.0, max_cloud_cover=30),
        PlanetaryComputerSearcher(),
    )
    if cube is None:
        print("no imagery"); return 1
    # floor-step can leave MORE than MAX_TIMESTEPS; the encoder's time-embedding table
    # holds exactly 12, so clamp (same fix as run_delineation_olmoearth).
    step = max(1, cube.sizes["time"] // MAX_TIMESTEPS)
    cube = cube.isel(time=slice(None, None, step)).isel(time=slice(0, MAX_TIMESTEPS))
    y_dim, x_dim = spatial_dims(cube)
    cube, side, aoi = _crop_to_square(cube, y_dim, x_dim)
    n_t = cube.sizes["time"]
    print(f"cube: {side}x{side} px, {n_t} timesteps\n")

    # --- shared truth + patch grid -------------------------------------------------
    feats = build_feature_stack(cube)
    ref_mask = rasterize_mask(fetch_nmripmap(aoi), aoi, (side, side))   # CORRECTED labels
    p_h = p_w = side // PATCH

    y_patch, valid_patch = _aggregate_to_patches(ref_mask, feats.valid_mask, p_h, p_w, PATCH)

    h, w = p_h * PATCH, p_w * PATCH
    yc = cube[y_dim].values[:h].reshape(p_h, PATCH).mean(1)
    xc = cube[x_dim].values[:w].reshape(p_w, PATCH).mean(1)
    yy, xx = np.meshgrid(yc, xc, indexing="ij")
    ll = np.column_stack([yy.reshape(-1), xx.reshape(-1)])

    yf, llf = y_patch[valid_patch], ll[valid_patch]
    blocks = assign_spatial_folds(llf[:, 0], llf[:, 1], block_deg=BLOCK_DEG)
    print(f"patches: {valid_patch.sum()} valid / {p_h*p_w}   "
          f"riparian: {100*yf.mean():.0f}%   spatial blocks: {len(set(blocks))}\n")
    if not 0 < yf.sum() < len(yf):
        print("single-class AOI"); return 1

    # --- arms ----------------------------------------------------------------------
    arms: dict[str, np.ndarray] = {
        "rf_features": patch_mean(feats.data, feats.valid_mask, p_h, p_w)[valid_patch],
    }
    model = load_olmoearth(DEFAULT_MODEL_ID)
    for pooling in ("mean_time", "temporal_stats", "concat_time"):
        emb = extract_embeddings(model, cube, aoi, patch_size=PATCH, pooling=pooling)
        arms[f"oe_{pooling}"] = emb.data.reshape(p_h * p_w, -1)[valid_patch]

    # --- identical spatial CV for every arm ----------------------------------------
    print(f"{'arm':22} {'dim':>5}  {'P':>5} {'R':>5} {'F1':>6} {'AUC':>6}")
    print("-" * 56)
    results = {}
    for name, x in arms.items():
        cv = spatial_cv(x, yf, blocks, n_folds=N_FOLDS, estimator=_cv_estimator())
        m = cv.metrics
        results[name] = {"dim": int(x.shape[1]), **{k: float(v) for k, v in m.items()}}
        print(f"{name:22} {x.shape[1]:>5}  {m.get('precision',0):>5.2f} {m.get('recall',0):>5.2f} "
              f"{m.get('f1',0):>6.3f} {m.get('roc_auc',0):>6.3f}")

    out = {
        "bbox": BBOX, "date_range": DATE_RANGE, "model": DEFAULT_MODEL_ID.value,
        "timesteps": int(n_t), "patch_size": PATCH, "block_deg": BLOCK_DEG,
        "n_folds": N_FOLDS, "n_patches": int(valid_patch.sum()),
        "riparian_frac": float(yf.mean()), "labels": "nmripmap_woody_corrected",
        "results": results,
    }
    with open("../docs/data/olmoearth-fair-test-2026-07-12.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote docs/data/olmoearth-fair-test-2026-07-12.json  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
