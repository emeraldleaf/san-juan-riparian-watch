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
from pystac_client.exceptions import APIError
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
    AGRICULTURE,
    BARE_CHANNEL,
    DEVELOPED,
    RIPARIAN_HERBACEOUS,
    RIPARIAN_WOODY_INTRODUCED,
    RIPARIAN_WOODY_NATIVE,
    UPLAND,
    WATER,
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

# Two mapping targets, each (negative labels → class 1, positive labels → class 2). "extent" =
# the whole woody corridor vs everything else; "invasive" = the introduced (IC) subset vs native.
_NON_RIPARIAN = (UPLAND, AGRICULTURE, WATER, BARE_CHANNEL, DEVELOPED, RIPARIAN_HERBACEOUS)
_RIPARIAN_WOODY = (RIPARIAN_WOODY_NATIVE, RIPARIAN_WOODY_INTRODUCED)
TARGETS = {
    "invasive": ((RIPARIAN_WOODY_NATIVE,), (RIPARIAN_WOODY_INTRODUCED,)),
    "extent": (_NON_RIPARIAN, _RIPARIAN_WOODY),
}


def _search_window(cat: pystac_client.Client, bbox: BBox, years: range) -> list:
    """Pool the least-cloudy TM/ETM+ growing-season scenes across every year in ``years``.

    A multi-year window (not a single year) is deliberate: single-year composites swing ~±0.5 pp
    (1999→2001 ran 2.1→1.2% here), so the trend only stabilises when a bad year is outvoted.
    """
    yrs = list(years)
    per_year = max(2, WINDOW_MAX // max(len(yrs), 1))   # a quota per year so no year is shut out
    pooled: list = []
    failed = []
    for year in yrs:
        got = _search_year(cat, bbox, year)
        if got is None:
            failed.append(year)
            continue
        pooled += _least_cloudy(got, per_year)          # each year contributes its best few
    if failed:
        logger.warning("  window %d–%d: %d year(s) had no usable search %s — composite is PARTIAL",
                       yrs[0], yrs[-1], len(failed), failed)
    return _least_cloudy(pooled, WINDOW_MAX)


def _least_cloudy(items: list, n: int) -> list:
    """The ``n`` least-cloudy items."""
    return sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100))[:n]


def _search_year(cat: pystac_client.Client, bbox: BBox, year: int) -> list | None:
    """One year's TM/ETM+ growing-season scenes, or None if the search never succeeded (retry-hardened)."""
    for attempt in range(6):
        try:
            return list(cat.search(
                collections=["landsat-c2-l2"], bbox=list(bbox),
                datetime=f"{year}-{GROW[0]}/{year}-{GROW[1]}",
                query={"eo:cloud_cover": {"lt": 40}, "platform": {"in": list(TM_FAMILY)}}).items())
        except (APIError, OSError, ValueError) as ex:   # STAC API / network / decode — transient, retry
            if attempt == 5:
                logger.warning("  %d: search failed after retries: %s", year, str(ex)[:50])
                return None
            time.sleep(2 + 2 * attempt)
    return None


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


def _label_grid(reader, bbox: BBox, affine, h: int, w: int, target: str) -> np.ndarray:
    """Rasterise NMRipMap for ``target`` → 2 positive, 1 negative, 0 nodata.

    Negatives are burned first and positives last, so the positive class wins on any overlap (a mixed
    stand counts as positive-present) — the same rule as ``build_invasive_labels``.
    """
    negatives, positives = TARGETS[target]
    polys = reader(bbox)
    feats = [{"type": "Feature", "geometry": p.geometry.__geo_interface__, "properties": {"class": cid}}
             for labels, cid in ((negatives, 1), (positives, 2))
             for p in polys if p.label in labels]
    return rasterize_labels({"type": "FeatureCollection", "features": feats}, affine, UTM, (h, w))


BandStats = tuple[np.ndarray, np.ndarray]  # (per-band median, per-band IQR)


def _band_stats(comp: np.ndarray) -> BandStats:
    """Per-band (median, IQR) over valid pixels — the reference for relative normalization."""
    flat = comp.reshape(comp.shape[0], -1)
    med = np.nanmedian(flat, axis=1)
    q1, q3 = np.nanpercentile(flat, [25, 75], axis=1)
    return med, np.where((q3 - q1) > 1e-6, q3 - q1, 1.0)


def _normalize_to_ref(comp: np.ndarray, ref: BandStats) -> np.ndarray:
    """Rescale each band so its (median, IQR) matches the reference composite's — relative radiometric
    normalization. Aligns Landsat-5 TM levels to the ETM+ training reference before indices, removing
    the systematic per-band sensor offset that raw indices carry (1990 was the unstable epoch)."""
    ref_med, ref_iqr = ref
    med, iqr = _band_stats(comp)
    out = np.empty_like(comp)
    for i in range(comp.shape[0]):
        out[i] = (comp[i] - med[i]) / iqr[i] * ref_iqr[i] + ref_med[i]
    return out


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Normalized difference (a − b)/(a + b), guarded against divide-by-zero."""
    return (a - b) / (a + b + 1e-6)


def _index_features(comp: np.ndarray) -> np.ndarray:
    """Cross-era-stable spectral indices from a (6,H,W) reflectance composite → ``(7, H, W)``.

    Bands are blue, green, red, nir08, swir16, swir22. Normalized-difference RATIOS cancel the
    multiplicative atmospheric/sensor gain that makes RAW reflectance drift between eras — so a
    2020-trained classifier keys on features that mean the same thing back through the Landsat record
    (raw-reflectance features made the historical trajectory swing ~1 pp with the compositing recipe).
    """
    _blue, green, red, nir, sw1, sw2 = comp
    return np.stack([_nd(nir, red), _nd(nir, sw1), _nd(green, sw1), _nd(nir, sw2),
                     _nd(green, red), _nd(sw1, sw2), _nd(green, nir)])


def _feature_matrix(comp: np.ndarray, ref: BandStats) -> np.ndarray:
    """Per-pixel feature rows ``(H*W, n_feat)`` — normalize to the reference, then index-stack."""
    feats = _index_features(_normalize_to_ref(comp, ref))
    return feats.reshape(feats.shape[0], -1).T


def train_rf(comp: np.ndarray, reader, bbox: BBox, affine, h: int, w: int,
             target: str) -> tuple[RandomForestClassifier, np.ndarray, BandStats]:
    """Train the ``target`` (positive-vs-negative) RF on the label-year composite.

    Returns ``(rf, train-median for impute, reference band-stats)`` — the composite's own band-stats
    become the reference every later epoch is normalized to (so it normalizes to itself, identity).
    """
    ref = _band_stats(comp)
    grid = _label_grid(reader, bbox, affine, h, w, target).reshape(-1)
    x = _feature_matrix(comp, ref)
    keep = np.isin(grid, (1, 2)) & np.isfinite(x).any(1)
    xk = x[keep]
    yk = (grid[keep] == 2).astype(int)
    med = np.nanmedian(xk, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", min_samples_leaf=1,
                                max_features="sqrt", n_jobs=-1, random_state=0)
    rf.fit(np.where(np.isfinite(xk), xk, med), yk)
    logger.info("trained %s RF: %d labelled px (%d positive / %d negative)",
                target, int(keep.sum()), int(yk.sum()), int((yk == 0).sum()))
    return rf, med, ref


def predict_extent(rf: RandomForestClassifier, med: np.ndarray, ref: BandStats, comp: np.ndarray,
                   affine, h: int, w: int, dest: Path, threshold: float, target: str) -> float:
    """Predict positive-class probability, vectorise ≥ threshold to WGS84 GeoJSON; return AOI fraction."""
    x = _feature_matrix(comp, ref)
    valid = np.isfinite(x).any(1)
    prob = rf.predict_proba(np.where(np.isfinite(x), x, med))[:, 1]
    prob[~valid] = 0.0
    binary = (prob >= threshold).reshape(h, w).astype("uint8")
    feats = [{"type": "Feature", "geometry": transform_geom(UTM, "EPSG:4326", g),
              "properties": {"class": target, "min_prob": threshold}}
             for g, v in shapes(binary, mask=binary.astype(bool), transform=affine) if v == 1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    frac = float(binary.sum()) / max(int(valid.sum()), 1)
    logger.info("  → %s : %d polygons, %.1f%% of valid AOI %s", dest.name, len(feats), 100 * frac, target)
    return frac


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the deep-time invasive-extent trajectory."""
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
    ap.add_argument("--target", choices=sorted(TARGETS), default="invasive",
                    help="'invasive' (IC vs native) or 'extent' (riparian woody vs non-riparian)")
    ap.add_argument("--out", type=Path, default=HERE / ".tmp/deep_invasives", help="GeoJSON output dir")
    ap.add_argument("--threshold", type=float, default=0.5, help="positive-class probability cutoff")
    return ap


def _map_epochs(cat: pystac_client.Client, a: argparse.Namespace, rf: RandomForestClassifier,
                med: np.ndarray, ref: BandStats, affine, h: int, w: int, train_comp: np.ndarray) -> None:
    """Map + report the ``a.target`` fraction for each epoch window, reusing the label-year composite."""
    logger.info("mapping %s per %d-year window:", a.target, 2 * a.half_width + 1)
    trajectory = {}
    for year in sorted(a.epochs):
        comp = (train_comp if year == a.label_year
                else season_composite(cat, FARM, year, a.half_width, affine, h, w))
        if comp is None:
            continue
        trajectory[year] = predict_extent(rf, med, ref, comp, affine, h, w,
                                          a.out / f"{a.target}_{year}.geojson", a.threshold, a.target)
    logger.info("── %s trajectory (fraction of valid AOI) ──", a.target)
    for year in sorted(trajectory):
        logger.info("  %d: %.1f%%", year, 100 * trajectory[year])


def main() -> int:
    """Train on the label-year window, map invasive extent per epoch window, log the trajectory."""
    ap = _build_arg_parser()
    a = ap.parse_args()
    if not 0.0 <= a.threshold <= 1.0:
        ap.error(f"--threshold must be a probability in [0, 1], got {a.threshold}")
    affine, h, w = _grid(FARM)
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    logger.info("label year %d — building training composite", a.label_year)
    train_comp = season_composite(cat, FARM, a.label_year, a.half_width, affine, h, w)
    if train_comp is None:
        raise SystemExit(f"no TM/ETM+ imagery for label year {a.label_year}")
    rf, med, ref = train_rf(train_comp, gdb_reader_factory(str(a.gdb)), FARM, affine, h, w, a.target)
    _map_epochs(cat, a, rf, med, ref, affine, h, w, train_comp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
