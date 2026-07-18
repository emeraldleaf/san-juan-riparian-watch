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

from riparian.labels import label_layer, nmripmap, validate_layer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_reach")

MALPAIS_BBOX = (-108.8217, 36.8096, -108.6729, 36.9508)  # Malpais Arroyo–San Juan (HUC12 140801051001)
FARMINGTON_BBOX = (-108.40, 36.66, -108.10, 36.80)  # the Phase-0 reach (AUC 0.752) — a cross-check
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
N_SCENES = 5  # median over the lowest-cloud peak-season scenes


def gdb_reader_factory(gdb_path: str):
    """A `LabeledPolygonReader` that loads NMRipMap from a local File Geodatabase.

    Bypasses the live ArcGIS query API (whose backend intermittently 500s) — and applies the **same
    crosswalk** as the live path by routing features through `nmripmap._to_labeled`, so it is not a
    'raw fetch' (which would be ~45% wrong). Same L2_Code → label → class mapping, different source.
    """
    import geopandas as gpd

    full = gpd.read_file(gdb_path).to_crs(4326)  # the GDB is ~15k features — read once, reproject to WGS84

    def _read(bbox: tuple[float, float, float, float]):
        # .cx slices by the (lon,lat) bounding box via the spatial index — the bbox must match the
        # frame's CRS (now 4326), which is why we reproject the whole layer first, not pass a raw bbox.
        gdf = full.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        feats = [
            {"geometry": geom.__geo_interface__, "properties": {"L2_Code": l2}}
            for geom, l2 in zip(gdf.geometry, gdf["L2_Code"], strict=True)
            if geom is not None
        ]
        return nmripmap._to_labeled(feats)

    return _read


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
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--reach", choices=["malpais", "farmington"], default="malpais")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MINX", "MINY", "MAXX", "MAXY"))
    ap.add_argument("--gdb", help="local NMRipMap File Geodatabase (bypasses the live ArcGIS query)")
    a = ap.parse_args()
    bbox = tuple(a.bbox) if a.bbox else (FARMINGTON_BBOX if a.reach == "farmington" else MALPAIS_BBOX)
    logger.info("validate_reach: %s bbox %s", a.reach, tuple(round(v, 4) for v in bbox))

    logger.info("fetching NMRipMap labels%s…", " (local GDB)" if a.gdb else " (live ArcGIS)")
    reader = gdb_reader_factory(a.gdb) if a.gdb else nmripmap.fetch_labeled
    fc, stats = label_layer.build_extent_labels(bbox, corridor=None, reader=reader)
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
