"""Phase 3B — the temporal test: does a 2020-trained model survive a *year* change?

3A isolated the sensor axis (2020 S2 → 2020 Landsat, +0.046 AUC). 3B isolates **time**: an RF
trained on Sentinel-2 2020 is scored at the **CSU 2017 field points** using **Landsat 2017**, and —
to keep space + sensor from contaminating the number — *also* at the same points using **Landsat
2020**. The 2020 score carries the space + sensor gap; the 2017 score carries space + sensor + time.
Their difference is the **temporal penalty** (assumes riparian-woody presence is stable 2017→2020 at
a point, which for woody extent over three years is reasonable — noted as a caveat).

Ground truth: 167 CSU points in the San Juan AOI (137 riparian-woody positives — tamarisk, Russian
olive, native, other woody — vs 30 non-riparian negatives: agriculture, absence, non-veg, upland).
The 2017 data is beetle-era; for *extent* (woody present/absent) that is a smaller confound than for
species, but it is real (Phase 3C).

Usage:
    PYTHONPATH=python-etl python phase3b_temporal.py \\
        --s2cube .tmp/xsensor.npz --gdb <path>/GRSJ_Version2_0Plus_North.gdb
    # run phase3a_cross_sensor.py first to build the S2-2020 training cube.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
import shapely.geometry as sg
from pyproj import Transformer
from rasterio.transform import Affine
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from riparian.labels import csu_points, label_layer, validate_layer  # noqa: E402
from validate_reach import gdb_reader_factory, rasterize_labels  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("phase3b")

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SJ_AOI = (-109.2, 36.2, -106.8, 37.8)          # San Juan basin filter for the CSU points
FARM = (-108.33, 36.70, -108.19, 36.79)         # the S2-2020 training cube's footprint (3A)
LS_BANDS = ["blue", "green", "red", "nir08", "swir16", "swir22"]
LS_SCALE, LS_OFF = 0.0000275, -0.2
POS_LABELS = {"tamarisk", "russian_olive", "native_riparian_woody", "other_woody"}
NEG_LABELS = {"agriculture", "absence", "non_veg", "upland_veg"}


def _search(cat, coll, bbox, s, e, query):
    for attempt in range(8):
        try:
            return list(cat.search(collections=[coll], bbox=list(bbox),
                                   datetime=f"{s}/{e}", query=query).items())
        except Exception as ex:  # noqa: BLE001 — STAC is intermittently slow; retry hard
            if attempt == 7:
                logger.warning("    search gave up: %s", str(ex)[:50])
                return None
            time.sleep(3 + 3 * attempt)


def _assign_points(scenes, pt_geoms):
    """Map the least-cloudy covering scene to each point index (scenes are cloud-sorted)."""
    geoms = [(sg.shape(it.geometry), it) for it in scenes]
    by_scene: dict[str, list[int]] = defaultdict(list)
    by_id: dict[str, object] = {}
    for i, p in enumerate(pt_geoms):
        for g, it in geoms:            # first hit = least cloudy scene that contains the point
            if g.contains(p):
                by_scene[it.id].append(i)
                by_id[it.id] = it
                break
    return by_scene, by_id


def _sample_scene(it, idxs, pts_lonlat, cube, mi) -> None:
    """Fill ``cube[mi, idxs, :]`` with reflectance sampled at the points from one scene."""
    with rasterio.open(it.assets["red"].href) as probe:
        crs = probe.crs
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xy = [tr.transform(pts_lonlat[i][0], pts_lonlat[i][1]) for i in idxs]
    for bi, band in enumerate(LS_BANDS):
        href = it.assets[band].href
        for attempt in range(4):
            try:
                with rasterio.open(href) as src:
                    vals = list(src.sample(xy, indexes=1))
                for k, i in enumerate(idxs):
                    r = float(vals[k][0]) * LS_SCALE + LS_OFF
                    cube[mi, i, bi] = r if 0.0 <= r <= 1.2 else np.nan
                break
            except Exception:  # noqa: BLE001 — COG read over HTTP is best-effort; retry then give up
                time.sleep(2 + 2 * attempt)


def _sample_month(cat, year, mi, pts_lonlat, pt_geoms, cube, aoi) -> bool:
    """Sample one month into ``cube[mi]``. False only if the STAC search failed transiently."""
    s, e = f"{year}-{mi + 1:02d}-01", f"{year}-{mi + 1:02d}-28"
    items = _search(cat, "landsat-c2-l2", aoi, s, e,
                    {"eo:cloud_cover": {"lt": 45}, "platform": {"eq": "landsat-8"}})
    if items is None:
        return False
    if not items:
        logger.info("  %d m%02d: no scenes", year, mi + 1)
        return True
    scenes = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100))
    by_scene, by_id = _assign_points(scenes, pt_geoms)
    for sid, idxs in by_scene.items():
        _sample_scene(by_id[sid], idxs, pts_lonlat, cube, mi)
    logger.info("  %d m%02d: %d pts from %d scene(s)", year, mi + 1,
                sum(len(v) for v in by_scene.values()), len(by_scene))
    return True


def sample_landsat_year(cat, year: int, pts_lonlat: np.ndarray, aoi) -> tuple[np.ndarray, list[int]]:
    """Point-sample a 6-band × 12-month Landsat cube at each point. Returns ((N,72), failed_months)."""
    n = len(pts_lonlat)
    cube = np.full((12, n, 6), np.nan, np.float32)
    pt_geoms = [sg.Point(lon, lat) for lon, lat in pts_lonlat]
    failed = [mi + 1 for mi in range(12)
              if not _sample_month(cat, year, mi, pts_lonlat, pt_geoms, cube, aoi)]
    feats = cube.transpose(1, 0, 2).reshape(n, 72)  # (N, 12*6) month-major, matching the S2 cube
    return feats, failed


def train_rf_on_s2_2020(s2cube: Path, gdb: str) -> RandomForestClassifier:
    """Reuse the 3A S2-2020 Farmington cube: RF on riparian-vs-corridor-neg pixels (all of them)."""
    d = np.load(s2cube)
    s2 = d["s2"]
    h, w = int(d["h"]), int(d["w"])
    affine = Affine(*d["affine"])
    fc, _ = label_layer.build_extent_labels(FARM, corridor=None, reader=gdb_reader_factory(gdb))
    mask = rasterize_labels(fc, affine, "EPSG:32612", (h, w)).reshape(-1)
    x = s2.reshape(72, -1).T
    pos, neg = validate_layer.POSITIVE_CLASS, validate_layer.CORRIDOR_NEGATIVE_CLASSES
    keep = np.isin(mask, (pos,) + tuple(neg)) & np.isfinite(x).any(1)
    y = (mask[keep] == pos).astype(int)
    med = np.nanmedian(x[keep], axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    xk = np.where(np.isfinite(x[keep]), x[keep], med)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                min_samples_leaf=1, max_features="sqrt", n_jobs=-1, random_state=0)
    rf.fit(xk, y)
    logger.info("trained RF on %d S2-2020 pixels (%d riparian)", keep.sum(), y.sum())
    return rf


def _impute_cols(x: np.ndarray) -> np.ndarray:
    med = np.nanmedian(x, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    return np.where(np.isfinite(x), x, med)


def _year_features(cat, year: int, lonlat: np.ndarray, aoi, cache: Path) -> np.ndarray:
    """Point-sampled Landsat features for one year, cached — but never a partial (failed) fetch."""
    if cache.exists():
        logger.info("loaded cached %d features", year)
        return np.load(cache)["feats"]
    feats, failed = sample_landsat_year(cat, year, lonlat, aoi)
    if failed:
        # Do not cache a partial fetch — a rerun must re-sample the timed-out months.
        logger.warning("  %d: transient-failed months %s — NOT caching; rerun to fill", year, failed)
    else:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, feats=feats)
    return feats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--s2cube", type=Path, default=HERE / ".tmp/xsensor.npz",
                    help="3A S2-2020 cube (.npz with h/w keys); run phase3a_cross_sensor.py first")
    ap.add_argument("--gdb", required=True, help="local NMRipMap File Geodatabase (training labels)")
    ap.add_argument("--cache", type=Path, default=HERE / ".tmp/phase3b",
                    help="per-year point-sample cache dir")
    a = ap.parse_args()

    pts = [p for p in csu_points.load_points()
           if SJ_AOI[0] <= p.lon <= SJ_AOI[2] and SJ_AOI[1] <= p.lat <= SJ_AOI[3]]
    pts = [p for p in pts if p.label in POS_LABELS or p.label in NEG_LABELS]
    lonlat = np.array([[p.lon, p.lat] for p in pts])
    y = np.array([1 if p.label in POS_LABELS else 0 for p in pts])
    pt_aoi = (float(lonlat[:, 0].min()) - 0.05, float(lonlat[:, 1].min()) - 0.05,
              float(lonlat[:, 0].max()) + 0.05, float(lonlat[:, 1].max()) + 0.05)
    logger.info("points: %d (%d riparian / %d non-riparian) over %s",
                len(pts), y.sum(), (y == 0).sum(), pt_aoi)

    rf = train_rf_on_s2_2020(a.s2cube, a.gdb)
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)

    scores = {}
    for year in (2020, 2017):
        feats = _year_features(cat, year, lonlat, pt_aoi, a.cache / f"landsat_{year}_pts.npz")
        p = rf.predict_proba(_impute_cols(feats))[:, 1]
        scores[year] = validate_layer.auc(p[y == 1], p[y == 0])
        logger.info("  %d: AUC=%.3f (point coverage %.0f%%)", year, scores[year],
                    100 * np.isfinite(feats).any(1).mean())

    logger.info("")
    logger.info("═══ Phase 3B — temporal penalty (RF trained on S2-2020) ═══")
    logger.info("  Landsat 2020 @ points (space+sensor)       AUC = %.3f", scores[2020])
    logger.info("  Landsat 2017 @ points (space+sensor+TIME)  AUC = %.3f", scores[2017])
    logger.info("  TEMPORAL PENALTY = %+.3f", scores[2020] - scores[2017])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
