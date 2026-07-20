"""Deployable riparian-extent inference — train on pooled NMRipMap reaches, map an AOI.

The first *product* artifact, not an experiment: an RF is trained on riparian-vs-corridor pixels
pooled from **several NMRipMap reaches** (the "widen beyond one reach" step, folded in), then run
over a target AOI's full Sentinel-2 grid to produce a **riparian-probability GeoTIFF** and a
**thresholded extent GeoJSON**. No database and no GPU — this is the on-demand batch inference the
hosting ADR (`decisions/2026-07-11-model-and-inference-hosting.md`) calls for; the GeoJSON drops
straight onto the MapLibre map.

Cross-reach generalisation is reported by holding out each training reach in turn (the honest
verdict from the methods doc — transfer, not in-domain fit).

Usage:
    PYTHONPATH=python-etl python deploy_extent_map.py \\
        --gdb <path>/GRSJ_Version2_0Plus_North.gdb --dest .tmp/deploy
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Pin GDAL/rasterio + Python temp to the DATA DRIVE before rasterio loads (receipt #17: GDAL keeps
# its own CPL_TMPDIR that TMPDIR does not cover; a COG-heavy run will otherwise fill the boot disk).
_TMP = Path(__file__).resolve().parent / ".tmp" / "gdaltmp"
_TMP.mkdir(parents=True, exist_ok=True)
for _v in ("TMPDIR", "TMP", "TEMP", "CPL_TMPDIR"):
    os.environ[_v] = str(_TMP)
os.environ.setdefault("GDAL_CACHEMAX", "256")

# These imports follow the temp-redirect above, which must run before rasterio/GDAL loads.
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import shapes  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

import time  # noqa: E402

import planetary_computer as pc  # noqa: E402
import pystac_client  # noqa: E402

from phase3a_cross_sensor import STAC, S2_BANDS, S2_OFF, S2_SCALE, UTM, _grid, _read_band  # noqa: E402
from rasterio.warp import transform_geom  # noqa: E402
from riparian.labels import label_layer, validate_layer  # noqa: E402
from validate_reach import gdb_reader_factory, rasterize_labels  # noqa: E402

N_SCENES = 4  # scenes per month to median-composite — aligned compositing (receipt #20), not single-scene

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("deploy")

# NM San Juan reaches with confirmed NMRipMap coverage, chosen for MORPHOLOGICAL DIVERSITY
# (the transfer diagnostic showed each reach is separable in-domain but boundaries don't transfer
# across morphology — so the pool must span types, not just count) (EPSG:4326).
TRAIN_REACHES = {
    "farmington": (-108.40, 36.66, -108.10, 36.80),      # San Juan/Animas confluence — wide river
    "malpais": (-108.8217, 36.8096, -108.6729, 36.9508),  # narrow arroyo — sparse/dry
    "kirtland": (-108.55, 36.67, -108.37, 36.81),         # San Juan mainstem, semi-arid downstream
    "aztec_animas": (-108.10, 36.79, -107.92, 36.93),     # Animas tributary — narrower, montane-fed
}
DEPLOY_AOI = (-108.10, 36.66, -107.92, 36.79)  # Bloomfield — held-out San Juan reach to map
CUBE_CACHE = HERE / ".tmp/cubes"  # per-bbox median cube cache — makes the multi-reach run resumable
POS = validate_layer.POSITIVE_CLASS
NEG = validate_layer.CORRIDOR_NEGATIVE_CLASSES


def _search_s2(cat, bbox, month: int):
    """Least-cloudy-first S2 items for one 2020 month; [] only after retries exhaust."""
    for attempt in range(6):
        try:
            items = list(cat.search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                                    datetime=f"2020-{month:02d}-01/2020-{month:02d}-28",
                                    query={"eo:cloud_cover": {"lt": 40}}).items())
            return sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100))
        except Exception:  # noqa: BLE001 — STAC is intermittently slow; retry hard
            time.sleep(2 + 2 * attempt)
    return []


def _fetch_s2(bbox):
    """S2-2020 12-month **median-mosaic** cube (receipt #20 aligned compositing).

    Each month is the pixel-wise median of the ``N_SCENES`` least-cloudy scenes — median is robust to
    the bright cloud outliers a single scene carries, and gives features that transfer across reaches
    (single-scene collapsed Farmington→Malpais to AUC 0.527). Returns (features (72,H,W), affine, h, w).
    """
    affine, h, w = _grid(bbox)
    key = "_".join(f"{v:.4f}" for v in bbox)
    cache = CUBE_CACHE / f"s2_{key}.npz"
    if cache.exists():
        logger.info("  cached cube %s", cache.name)
        return np.load(cache)["s2"], affine, h, w
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    cube = []
    for m in range(1, 13):
        items = _search_s2(cat, bbox, m)[:N_SCENES]
        if not items:
            cube.append(np.full((6, h, w), np.nan, np.float32))
            logger.info("  m%02d: no scenes", m)
            continue
        band_meds = []
        for band in S2_BANDS:
            scenes = np.stack([_read_band(it.assets[band].href, S2_SCALE, S2_OFF, affine, h, w)
                               for it in items])
            band_meds.append(np.nanmedian(scenes, axis=0).astype(np.float32))
        cube.append(np.stack(band_meds))
        logger.info("  m%02d: median of %d scenes", m, len(items))
    s2 = np.concatenate(cube, 0)
    CUBE_CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(cache, s2=s2)
    return s2, affine, h, w


def labeled_pixels(bbox, gdb: str) -> tuple[np.ndarray, np.ndarray]:
    """Fetch S2 + rasterise NMRipMap; return (X_labeled (n,72), y) for riparian-vs-corridor."""
    s2, affine, h, w = _fetch_s2(bbox)
    fc, stats = label_layer.build_extent_labels(bbox, corridor=None, reader=gdb_reader_factory(gdb))
    mask = rasterize_labels(fc, affine, UTM, (h, w)).reshape(-1)
    x = s2.reshape(72, -1).T
    keep = np.isin(mask, (POS,) + tuple(NEG)) & np.isfinite(x).any(1)
    logger.info("  labels: %d riparian + %d corridor-neg polygons → %d px",
                stats.n_positive, stats.n_negative, int(keep.sum()))
    return x[keep], (mask[keep] == POS).astype(int)


def _impute(train_x: np.ndarray, x: np.ndarray) -> np.ndarray:
    med = np.nanmedian(train_x, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    return np.where(np.isfinite(x), x, med)


def _new_rf() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                  min_samples_leaf=1, max_features="sqrt", n_jobs=-1, random_state=0)


def cross_reach_report(per_reach: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
    """Hold each reach out in turn; report transfer AUC — the honest generalisation number."""
    names = list(per_reach)
    if len(names) < 2:
        return
    logger.info("cross-reach transfer (train on the rest, test held-out):")
    for held in names:
        tr_x = np.vstack([per_reach[n][0] for n in names if n != held])
        tr_y = np.concatenate([per_reach[n][1] for n in names if n != held])
        te_x, te_y = per_reach[held]
        rf = _new_rf()
        rf.fit(_impute(tr_x, tr_x), tr_y)
        p = rf.predict_proba(_impute(tr_x, te_x))[:, 1]
        auc = validate_layer.auc(p[te_y == 1], p[te_y == 0])
        logger.info("  → %-12s AUC = %.3f  (%d px)", held, auc, len(te_y))


def _write_geotiff(prob: np.ndarray, affine, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dest, "w", driver="GTiff", height=prob.shape[0], width=prob.shape[1],
                       count=1, dtype="float32", crs=UTM, transform=affine,
                       compress="deflate", nodata=np.nan) as dst:
        dst.write(prob.astype("float32"), 1)
    logger.info("wrote %s", dest)


def _write_geojson(prob: np.ndarray, affine, dest: Path, threshold: float) -> int:
    """Vectorise prob >= threshold to WGS84 polygons; return polygon count."""
    binary = (np.nan_to_num(prob) >= threshold).astype("uint8")
    feats = []
    for geom, val in shapes(binary, mask=binary.astype(bool), transform=affine):
        if val != 1:
            continue
        wgs = transform_geom(UTM, "EPSG:4326", geom)
        feats.append({"type": "Feature", "geometry": wgs,
                      "properties": {"class": "riparian", "min_prob": threshold}})
    fc = {"type": "FeatureCollection", "features": feats}
    dest.write_text(json.dumps(fc))
    logger.info("wrote %s (%d polygons ≥ %.2f)", dest, len(feats), threshold)
    return len(feats)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gdb", required=True, help="local NMRipMap File Geodatabase")
    ap.add_argument("--dest", type=Path, default=HERE / ".tmp/deploy", help="output dir")
    ap.add_argument("--threshold", type=float, default=0.5, help="riparian probability cut for polygons")
    a = ap.parse_args()

    logger.info("== training on %d NMRipMap reaches ==", len(TRAIN_REACHES))
    per_reach = {}
    for name, bbox in TRAIN_REACHES.items():
        logger.info("reach %s %s", name, bbox)
        per_reach[name] = labeled_pixels(bbox, a.gdb)

    cross_reach_report(per_reach)

    x = np.vstack([v[0] for v in per_reach.values()])
    y = np.concatenate([v[1] for v in per_reach.values()])
    rf = _new_rf()
    rf.fit(_impute(x, x), y)
    logger.info("deployed model: %d px pooled (%d riparian) from %d reaches",
                len(y), int(y.sum()), len(per_reach))

    logger.info("== inference over deploy AOI %s ==", DEPLOY_AOI)
    s2, affine, h, w = _fetch_s2(DEPLOY_AOI)
    grid_x = s2.reshape(72, -1).T
    valid = np.isfinite(grid_x).any(1)
    prob = np.full(h * w, np.nan, np.float32)
    prob[valid] = rf.predict_proba(_impute(x, grid_x[valid]))[:, 1]
    prob = prob.reshape(h, w)
    logger.info("predicted %d valid px; %.1f%% ≥ %.2f (riparian)",
                int(valid.sum()), 100 * (np.nan_to_num(prob) >= a.threshold).mean(), a.threshold)

    _write_geotiff(prob, affine, a.dest / "riparian_extent_prob.tif")
    n_poly = _write_geojson(prob, affine, a.dest / "riparian_extent.geojson", a.threshold)
    logger.info("== DEPLOYABLE: %d riparian polygons over the AOI ==", n_poly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
