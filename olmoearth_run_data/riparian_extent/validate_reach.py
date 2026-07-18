"""Validate the NMRipMap label layer against Sentinel-2 2020 NDVI for an arbitrary reach (bbox).

Issue #51 — Phase 0 validated one reach (Farmington, separability AUC 0.752) and flagged "one reach,
not the basin." This scores a **second** reach the *same* way — `validate_layer.py`, peak-season,
water-excluded — so the number is directly comparable to 0.752, unlike the ad-hoc distance-to-mainstem
harness the Malpais reach note used.

It fetches its own S2 (not a materialised cube), so it works for any reach given a bbox:
  1. NMRipMap labels for the bbox — via the tested `label_layer.build_extent_labels`.
  2. Peak-season (Jun–Aug) median NDVI for the bbox from Planetary Computer, one MGRS tile.
  3. Rasterise labels onto the NDVI grid; separability (riparian vs corridor-neg 3/4) + a global,
     pooled shift test — the same contract as `validate_materialized.py`.

    PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/validate_reach.py \
        [minx miny maxx maxy]     # defaults to the Malpais Arroyo–San Juan HUC12
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
import shapely.geometry
import shapely.ops
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rasterio.windows import transform as window_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-etl"))

from riparian.labels import label_layer, validate_layer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_reach")

MALPAIS_BBOX = (-108.8217, 36.8096, -108.6729, 36.9508)  # Malpais Arroyo–San Juan (HUC12 140801051001)
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
N_SCENES = 5  # median over the lowest-cloud peak-season scenes


def fetch_s2_ndvi(bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, object, str]:
    """Peak-season (Jun–Aug 2020) median NDVI for the bbox, on one MGRS tile's 10 m grid.

    Returns ``(ndvi, transform, crs)`` — the affine + CRS pin the grid so labels rasterise onto it.
    """
    cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                            datetime="2020-06-01/2020-08-31",
                            query={"eo:cloud_cover": {"lt": 20}}).items())
    if not items:
        raise RuntimeError("no low-cloud peak-season S2 over this bbox")
    # one tile keeps every scene on the same grid; take the tile of the least-cloudy scene
    items.sort(key=lambda i: i.properties["eo:cloud_cover"])
    tile = items[0].properties.get("s2:mgrs_tile")
    scenes = [i for i in items if i.properties.get("s2:mgrs_tile") == tile][:N_SCENES]
    logger.info("  %d peak-season scenes on tile %s (median of %d least-cloudy)",
                len(items), tile, len(scenes))

    ndvis, transform, crs = [], None, None
    for it in scenes:
        with rasterio.open(it.assets["B04"].href) as r4:
            utm = transform_bounds("EPSG:4326", r4.crs, *bbox)
            win = from_bounds(*utm, transform=r4.transform)
            red = r4.read(1, window=win).astype("float32")
            if transform is None:
                transform, crs = window_transform(win, r4.transform), r4.crs.to_string()
        with rasterio.open(it.assets["B08"].href) as r8:
            nir = r8.read(1, window=from_bounds(*utm, transform=r8.transform)).astype("float32")
        denom = nir + red
        with np.errstate(invalid="ignore", divide="ignore"):
            ndvis.append(np.where(denom > 0, (nir - red) / denom, np.nan))
    # crop all to the smallest common shape (windows can differ by a pixel across scenes)
    h = min(a.shape[0] for a in ndvis)
    w = min(a.shape[1] for a in ndvis)
    return np.nanmedian(np.stack([a[:h, :w] for a in ndvis]), axis=0), transform, crs


def rasterize_labels(fc: dict, transform: object, crs: str, shape: tuple[int, int]) -> np.ndarray:
    """Rasterise the label FeatureCollection (EPSG:4326) onto the NDVI grid, by class id."""
    to_grid = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    shapes = []
    for feat in fc["features"]:
        cid = int(feat["properties"]["class"])
        if cid == 0:
            continue
        geom = shapely.ops.transform(to_grid, shapely.geometry.shape(feat["geometry"]))
        shapes.append((geom, cid))
    if not shapes:
        return np.zeros(shape, dtype="int32")
    return rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="int32")


def _global_shift_best(ndvi: np.ndarray, mask: np.ndarray) -> tuple[tuple[int, int], float, float]:
    """Best registration offset by pooled AUC (same rule as validate_layer.best_shift)."""
    scores = {}
    for dy in validate_layer.SHIFTS:
        for dx in validate_layer.SHIFTS:
            shifted = validate_layer.translate(mask, dy, dx)
            pos = ndvi[shifted == validate_layer.POSITIVE_CLASS]
            neg = ndvi[np.isin(shifted, validate_layer.CORRIDOR_NEGATIVE_CLASSES)]
            pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
            if pos.size and neg.size:
                scores[(dy, dx)] = validate_layer.auc(pos, neg)
    best = validate_layer.best_shift(scores)
    return best, scores[best], scores[(0, 0)]


def main() -> int:
    args = sys.argv[1:]
    bbox = tuple(float(x) for x in args[:4]) if len(args) >= 4 else MALPAIS_BBOX
    logger.info("validate_reach: bbox %s", tuple(round(v, 4) for v in bbox))

    logger.info("fetching NMRipMap labels…")
    fc, stats = label_layer.build_extent_labels(bbox, corridor=None)
    logger.info("  %d riparian + %d corridor-negative polygons", stats.n_positive, stats.n_negative)

    logger.info("fetching S2 2020 peak-season NDVI…")
    ndvi, transform, crs = fetch_s2_ndvi(bbox)
    mask = rasterize_labels(fc, transform, crs, ndvi.shape)

    pos = ndvi[mask == validate_layer.POSITIVE_CLASS]
    neg = ndvi[np.isin(mask, validate_layer.CORRIDOR_NEGATIVE_CLASSES)]
    sep = validate_layer.separability(pos, neg)
    best, best_auc, unshifted = _global_shift_best(ndvi, mask)

    logger.info("")
    logger.info("═══ Malpais reach — validate_layer, peak-season, water-excluded ═══")
    logger.info("  separability AUC = %.3f  [%s]   (Farmington: 0.752)", sep.auc, sep.verdict)
    logger.info("  riparian median NDVI %.3f  vs  corridor-negative %.3f",
                sep.median_ndvi_positive, sep.median_ndvi_negative)
    logger.info("  n = %d riparian px / %d corridor-negative px", sep.n_positive, sep.n_negative)
    logger.info("  global shift test: best %s (pooled AUC %.3f vs unshifted %.3f)",
                best, best_auc, unshifted)
    ok = sep.verdict != "BROKEN" and best == (0, 0)
    logger.info("  gate: %s", "✅ PASS" if ok else "❌ FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
