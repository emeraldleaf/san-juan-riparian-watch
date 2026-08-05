"""Deep-time invasive-woody extent over a reach — a Landsat trajectory.

Trains an RF on NMRipMap's invasive class (``IC`` = tamarisk + Russian olive, *combined* — the labels
do not separate the two) vs native riparian, then maps invasive extent per epoch back through the
Landsat record. To keep year-to-year change meaning *vegetation* change rather than *sensor* change,
the whole trajectory stays on the **TM/ETM+ sensor family** (Landsat-5 + Landsat-7): train on 2020
ETM+, predict TM back to 1990 — OLI (Landsat-8) is deliberately excluded.

⚠ **Read the trend, not the year.** The labels are a 2020 snapshot and there is no ground truth before
~2018, so any single deep-time map is an *unvalidated reconstruction*. Held-constant method + sensor
makes the *relative* change (did the footprint grow?) far more trustworthy than any epoch's absolute
accuracy. Growing-season median composite (6 bands) — coarser than the 12-month phenology cube, so
in-domain separability is lower than the 0.85 that cube reached; it is what the deep record supports.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import planetary_computer as pc
import pystac_client
from rasterio.features import shapes
from rasterio.warp import transform_geom
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from phase3a_cross_sensor import (
    LS_BANDS,
    LS_OFF,
    LS_SCALE,
    STAC,
    UTM,
    _grid,
    _read_band,
)
from riparian.labels.nmripmap import (
    RIPARIAN_WOODY_INTRODUCED,
    RIPARIAN_WOODY_NATIVE,
)
from validate_reach import gdb_reader_factory, rasterize_labels

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("deep-invasives")

BBox = tuple[float, float, float, float]
FARM: BBox = (-108.33, 36.70, -108.19, 36.79)     # Farmington reach — best-labelled NM reach
TM_FAMILY = ("landsat-5", "landsat-7")            # exclude OLI so the trajectory holds one sensor family
GROW = ("06-01", "08-31")                         # peak growing season
WINDOW_MAX = 18                                   # cap of least-cloudy scenes to median across a window
HALF_WIDTH = 2                                     # ±2 yr → 5-yr windows; single years vary ~±0.5 pp,
#                                                   so a multi-year median is what makes the trend robust


def _search_window(cat: pystac_client.Client, bbox: BBox, years: range) -> list:
    """Pool the least-cloudy TM/ETM+ growing-season scenes across every year in ``years``.

    A multi-year window (not a single year) is deliberate: single-year composites swing ~±0.5 pp
    (1999→2001 ran 2.1→1.2% here), so the trend only stabilises when a bad year is outvoted.
    """
    pooled: list = []
    for year in years:
        for attempt in range(6):
            try:
                pooled += list(cat.search(
                    collections=["landsat-c2-l2"], bbox=list(bbox),
                    datetime=f"{year}-{GROW[0]}/{year}-{GROW[1]}",
                    query={"eo:cloud_cover": {"lt": 40}, "platform": {"in": list(TM_FAMILY)}}).items())
                break
            except Exception as ex:  # noqa: BLE001 — STAC is intermittently slow; retry then give up
                if attempt == 5:
                    logger.warning("  %d: search failed: %s", year, str(ex)[:50])
                else:
                    time.sleep(2 + 2 * attempt)
    return sorted(pooled, key=lambda x: x.properties.get("eo:cloud_cover", 100))[:WINDOW_MAX]


def season_composite(cat: pystac_client.Client, bbox: BBox, center: int, half_width: int,
                     affine, h: int, w: int) -> np.ndarray | None:
    """Per-band growing-season median over a ``center ± half_width`` year window → ``(6, h, w)`` or None."""
    years = range(center - half_width, center + half_width + 1)
    items = _search_window(cat, bbox, years)
    if not items:
        logger.info("  %d±%d: no TM/ETM+ scenes", center, half_width)
        return None
    plats = {it.properties.get("platform", "?") for it in items}
    bands = [np.nanmedian(
        np.stack([_read_band(it.assets[b].href, LS_SCALE, LS_OFF, affine, h, w) for it in items]),
        axis=0) for b in LS_BANDS]
    comp = np.stack(bands)
    logger.info("  %d (%d–%d): %d scene(s) %s → composite, %.0f%% pixels valid",
                center, years[0], years[-1], len(items), sorted(plats),
                100 * np.isfinite(comp).any(0).mean())
    return comp


def _invasive_label_grid(reader, bbox: BBox, affine, h: int, w: int) -> np.ndarray:
    """Rasterise NMRipMap woody labels → 2 invasive (IC/introduced), 1 native, 0 nodata.

    Native is listed first and invasive last so invasive wins on any overlap (a mixed
    native-introduced stand counts as invasive-present) — the same rule as ``build_invasive_labels``.
    """
    polys = reader(bbox)
    feats = [{"type": "Feature", "geometry": p.geometry.__geo_interface__, "properties": {"class": cid}}
             for lab, cid in ((RIPARIAN_WOODY_NATIVE, 1), (RIPARIAN_WOODY_INTRODUCED, 2))
             for p in polys if p.label == lab]
    return rasterize_labels({"type": "FeatureCollection", "features": feats}, affine, UTM, (h, w))


def train_invasive_rf(comp: np.ndarray, reader, bbox: BBox, affine, h: int,
                      w: int) -> tuple[RandomForestClassifier, np.ndarray]:
    """Train invasive(IC)-vs-native RF on the label-year composite; return (rf, train-median for impute)."""
    grid = _invasive_label_grid(reader, bbox, affine, h, w).reshape(-1)
    x = comp.reshape(len(LS_BANDS), -1).T
    keep = np.isin(grid, (1, 2)) & np.isfinite(x).any(1)
    xk = x[keep]
    yk = (grid[keep] == 2).astype(int)
    med = np.nanmedian(xk, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", min_samples_leaf=1,
                                max_features="sqrt", n_jobs=-1, random_state=0)
    rf.fit(np.where(np.isfinite(xk), xk, med), yk)
    logger.info("trained RF: %d labelled px (%d invasive / %d native)",
                int(keep.sum()), int(yk.sum()), int((yk == 0).sum()))
    return rf, med


def predict_extent(rf: RandomForestClassifier, med: np.ndarray, comp: np.ndarray,
                   affine, h: int, w: int, dest: Path, threshold: float) -> float:
    """Predict invasive probability, vectorise ≥ threshold to WGS84 GeoJSON; return AOI invasive fraction."""
    x = comp.reshape(len(LS_BANDS), -1).T
    valid = np.isfinite(x).any(1)
    prob = rf.predict_proba(np.where(np.isfinite(x), x, med))[:, 1]
    prob[~valid] = 0.0
    binary = (prob >= threshold).reshape(h, w).astype("uint8")
    feats = [{"type": "Feature", "geometry": transform_geom(UTM, "EPSG:4326", g),
              "properties": {"class": "invasive_woody", "min_prob": threshold}}
             for g, v in shapes(binary, mask=binary.astype(bool), transform=affine) if v == 1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    frac = float(binary.sum()) / max(int(valid.sum()), 1)
    logger.info("  → %s : %d polygons, %.1f%% of valid AOI invasive", dest.name, len(feats), 100 * frac)
    return frac


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gdb", type=Path,
                    default=HERE.parents[1] / ".tmp/nmripmap_gdb"
                            / "GilaRegionSanJuan_Version2.0Plus_North" / "GRSJ_Version2_0Plus_North.gdb",
                    help="local NMRipMap File Geodatabase for invasive labels (bypasses the live service)")
    ap.add_argument("--label-year", type=int, default=2020, help="imagery year paired with the 2020 labels")
    ap.add_argument("--epochs", type=int, nargs="+", default=[1990, 2000, 2010, 2020],
                    help="trajectory window CENTER years to map (TM/ETM+ only)")
    ap.add_argument("--half-width", type=int, default=HALF_WIDTH,
                    help="composite window half-width in years (±); 2 → 5-year windows")
    ap.add_argument("--out", type=Path, default=HERE / ".tmp/deep_invasives", help="GeoJSON output dir")
    ap.add_argument("--threshold", type=float, default=0.5, help="invasive-probability cutoff for extent")
    a = ap.parse_args()

    affine, h, w = _grid(FARM)
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    logger.info("label year %d — building training composite", a.label_year)
    train_comp = season_composite(cat, FARM, a.label_year, a.half_width, affine, h, w)
    if train_comp is None:
        raise SystemExit(f"no TM/ETM+ imagery for label year {a.label_year}")
    reader = gdb_reader_factory(str(a.gdb))
    rf, med = train_invasive_rf(train_comp, reader, FARM, affine, h, w)

    logger.info("mapping invasive extent per %d-year window:", 2 * a.half_width + 1)
    trajectory = {}
    for year in sorted(a.epochs):
        comp = train_comp if year == a.label_year else season_composite(cat, FARM, year, a.half_width, affine, h, w)
        if comp is None:
            continue
        trajectory[year] = predict_extent(rf, med, comp, affine, h, w,
                                          a.out / f"invasive_{year}.geojson", a.threshold)
    logger.info("── invasive-extent trajectory (fraction of valid AOI) ──")
    for year in sorted(trajectory):
        logger.info("  %d: %.1f%%", year, 100 * trajectory[year])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
