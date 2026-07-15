"""Validate the materialised label layer against the imagery — reproducibly, water excluded.

The AUC-0.777 headline in the Phase-0 record came from an ad-hoc harness on NMRipMap polygons that
was never committed, and it scored riparian against **all** non-riparian classes — water included.
Water is trivially separable from vegetation by NDVI, so that number was optimistic.

This script recomputes it honestly, from the **materialised dataset** — the exact pixels the model
will train on — using the corridor-negative contract (agriculture + other, not water) from
``riparian.labels.validate_layer``. Run it after `dataset materialize`:

    PYTHONPATH=python-etl \
    .venv-olmoearth/bin/python olmoearth_run_data/riparian_extent/validate_materialized.py \
        olmoearth_run_data/riparian_extent/dataset

NDVI = (B08 − B04) / (B08 + B04), taken as the per-pixel **median across the 12 monthly mosaics**
(peak season is already June–August). The geotiff band order is
``B01 B02 B03 B04 B05 B06 B07 B08 B8A B09 B11 B12`` → Red = band 4, NIR = band 8 (1-indexed).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-etl"))

from riparian.labels import validate_layer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_materialized")

RED_BAND = 4  # B04, 1-indexed in the stacked geotiff
NIR_BAND = 8  # B08


def _median_ndvi(window: Path) -> np.ndarray:
    """Per-pixel median NDVI across a window's monthly Sentinel-2 mosaics."""
    tifs = sorted(window.glob("layers/sentinel2*/*/geotiff.tif"))
    if not tifs:
        raise FileNotFoundError(f"no sentinel2 mosaics in {window}")
    ndvis = []
    for tif in tifs:
        with rasterio.open(tif) as src:
            red = src.read(RED_BAND).astype("float32")
            nir = src.read(NIR_BAND).astype("float32")
        denom = nir + red
        with np.errstate(invalid="ignore", divide="ignore"):
            ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)
        ndvis.append(ndvi)
    return np.nanmedian(np.stack(ndvis), axis=0)


def _label(window: Path) -> np.ndarray:
    with rasterio.open(window / "layers/label_raster/label/geotiff.tif") as src:
        return src.read(1)


def main() -> int:
    dataset = Path(sys.argv[1] if len(sys.argv) > 1 else "olmoearth_run_data/riparian_extent/dataset")
    windows = sorted((dataset / "windows").glob("*/*/"))
    logger.info("validating %d windows in %s", len(windows), dataset)

    # Cache each window's NDVI + mask once; both the separability and the (global) shift test reuse
    # them. Per-window shift testing is meaningless — a 32×32 tile has too few pixels, so AUC swings
    # by ±0.3 on a 1 px shift purely from sampling. Registration is a *global* property (a CRS
    # offset shifts every window the same way), so we pool across ALL windows per candidate shift.
    grids = [(_median_ndvi(w), _label(w)) for w in windows]

    pos = np.concatenate([ndvi[mask == validate_layer.POSITIVE_CLASS] for ndvi, mask in grids])
    neg = np.concatenate(
        [ndvi[np.isin(mask, validate_layer.CORRIDOR_NEGATIVE_CLASSES)] for ndvi, mask in grids]
    )
    sep = validate_layer.separability(pos, neg)

    # Global shift test: for each offset, translate every window's mask the same way, pool the
    # pixels, and score one AUC over ~140k samples. Noise averages out; a systematic offset does not.
    shift_scores: dict[tuple[int, int], float] = {}
    for dy in validate_layer.SHIFTS:
        for dx in validate_layer.SHIFTS:
            p, n = [], []
            for ndvi, mask in grids:
                shifted = validate_layer._translate(mask, dy, dx)
                p.append(ndvi[shifted == validate_layer.POSITIVE_CLASS])
                n.append(ndvi[np.isin(shifted, validate_layer.CORRIDOR_NEGATIVE_CLASSES)])
            shift_scores[(dy, dx)] = validate_layer.auc(np.concatenate(p), np.concatenate(n))
    raw_best = min(shift_scores, key=lambda k: (-shift_scores[k], abs(k[0]) + abs(k[1])))
    best_shift = (
        (0, 0)
        if shift_scores[raw_best] - shift_scores[(0, 0)] < validate_layer.ALIGNMENT_TOLERANCE
        else raw_best
    )

    logger.info("")
    logger.info("═══ HONEST separability (riparian vs agriculture+other, water EXCLUDED) ═══")
    logger.info("  AUC = %.3f  [%s]", sep.auc, sep.verdict)
    logger.info("  riparian median NDVI %.3f  vs  corridor-negative %.3f",
                sep.median_ndvi_positive, sep.median_ndvi_negative)
    logger.info("  n = %d riparian px / %d corridor-negative px", sep.n_positive, sep.n_negative)
    logger.info("  global shift test: best offset %s (pooled AUC %.3f vs unshifted %.3f)",
                best_shift, shift_scores[best_shift], shift_scores[(0, 0)])

    ok = sep.verdict != "BROKEN" and best_shift == (0, 0)
    logger.info("  gate: %s", "✅ PASS" if ok else "❌ FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
