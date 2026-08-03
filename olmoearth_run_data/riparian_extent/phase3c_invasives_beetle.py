"""Phase 3C — native-vs-invasive, and does the signal survive the beetle (CPU/RF arm).

The Stage-2 analogue of the settled Stage-1 extent LORO result, and the RF arm of the
`docs/specs/2026-08-01-stage2-invasives-beetle-gate.md` gate. Two CPU-only tests on the CSU 2017
field points, point-sampled from Landsat (the only sensor reaching pre-beetle, 1984→):

* **Test A — separability.** Spatial-CV (grouped by field trip) RF on invasive-vs-native from the
  2020 phenology cube. Is the species signal even there? Pre-registered gate: AUROC ≥ 0.75.
* **Test C1 — the beetle deep-time inversion.** The 3B trick: the *same points*, the *same CV folds*,
  scored on 2020 vs 2000 Landsat. A 2020-trained model learns "tamarisk browns before native"; pre-beetle
  tamarisk stays green *longer*, so the cue's sign flips. Pre-registered prediction: **AUROC(2000) < 0.5**
  — actively wrong, not just degraded. ⚠ **Confound:** 2000 is Landsat-5 (TM) and 2020 is Landsat-8 (OLI),
  so the raw C1 gap carries *sensor + beetle*, not the beetle alone. 3A measured the S2→Landsat sensor
  penalty at only +0.046 AUC, far short of a sign flip — so an *inversion* can't be a sensor artifact —
  but the gap's magnitude must be read against that control, per the spec.  Russian olive (not
  beetle-defoliated) is the built-in negative control: it should NOT invert.

This is a scaffold: it runs the moment `TabletData_2017.csv` (CSU, CC BY-SA, ~326 KB from
mountainscholar) is on disk. It reuses the tested 3B point-sampler verbatim, adding only
platform-per-year (Landsat-5 TM for 2000, Landsat-8 OLI for 2015/2020; `landsat-c2-l2` serves
common-name bands across both). No GPU — the FM arm (Tests B + the GO/ABORT) is the Stage-1 LORO
machinery pointed at species labels, spec'd separately and run only if this arm justifies the spend.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import planetary_computer as pc
import pystac_client
import shapely.geometry as sg
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

# Reuse the 3B point-sampler verbatim — same retry/scene-assignment/COG-read logic, tested in prod.
from phase3b_temporal import (
    SJ_AOI,
    STAC,
    _assign_points,
    _sample_scene,
    _search,
)
from riparian.labels import csu_points, validate_layer

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("phase3c")

BBox = tuple[float, float, float, float]


class StacClient(Protocol):
    """The minimal STAC search surface used here — ``pystac_client.Client`` satisfies it."""

    def search(self, **kwargs: Any) -> Any:
        """Mirror ``pystac_client.Client.search`` — kwargs: collections, bbox, datetime, query."""
        ...


# Species task: invasive (tamarisk + Russian olive) vs native riparian woody. Other/non-riparian
# labels are dropped — this gate is native-vs-invasive, not presence/absence (that was Stage 1).
# Both sets derive from csu_points so a new species there can't leave this gate scoring a stale set.
INVASIVE = csu_points.INVASIVE_LABELS
NATIVE = frozenset({csu_points.NATIVE_RIPARIAN_WOODY})
# The training year IS the label vintage — one derived fact, never a re-hardcoded literal.
TRAIN_YEAR = validate_layer.IMAGERY_YEAR
CV_SPLITS = 5
SEPARABILITY_GATE = 0.75  # Test A pre-registered bar: below this the species signal is too weak → ABORT
MIN_TAXON = 8  # min points per class to attempt a taxon-vs-native fold split (in-basin labels are scarce)


def _platform_for_year(year: int) -> str:
    """The Landsat platform that actually flew in ``year``.

    Landsat-8 (OLI) launched 2013, so pre-beetle years must come from Landsat-5 (TM, 1984–2013).
    The `landsat-c2-l2` collection normalizes both to common-name band assets, so features align.
    """
    return "landsat-8" if year >= 2013 else "landsat-5"


def _month_range(year: int, mi: int) -> tuple[str, str]:
    """``(start, end)`` spanning the *whole* calendar month ``mi`` (0-based), with Dec→Jan rollover.

    End is the first day of the following month so every day (28/29/30/31) is included — a fixed
    ``-28`` would silently drop days 29–31 and the scenes on them.
    """
    month = mi + 1
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return start, end


def _sample_month(cat: StacClient, year: int, mi: int, pts_lonlat: np.ndarray,
                  pt_geoms: list[sg.Point], cube: np.ndarray, aoi: BBox) -> bool:
    """Sample month ``mi`` into ``cube[mi]`` from the platform that flew in ``year``.

    A platform-aware twin of the 3B helper (which hard-codes Landsat-8); everything downstream —
    scene assignment, COG sampling — is the shared, tested 3B code.
    """
    s, e = _month_range(year, mi)
    items = _search(cat, "landsat-c2-l2", aoi, s, e,
                    {"eo:cloud_cover": {"lt": 45}, "platform": {"eq": _platform_for_year(year)}})
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


def sample_year(cat: StacClient, year: int, lonlat: np.ndarray,
                aoi: BBox) -> tuple[np.ndarray, list[int]]:
    """Point-sample a 6-band × 12-month Landsat cube at each point.

    Args:
        cat: An opened STAC client (``pystac_client.Client``).
        year: Calendar year to sample; selects the platform via ``_platform_for_year``.
        lonlat: ``(N, 2)`` point coordinates in EPSG:4326.
        aoi: ``(minx, miny, maxx, maxy)`` search bbox in EPSG:4326.

    Returns:
        ``(features (N, 72) month-major, failed_month_numbers)`` — a non-empty second element
        means the fetch was partial and must not be cached.
    """
    n = len(lonlat)
    cube = np.full((12, n, 6), np.nan, np.float32)
    pt_geoms = [sg.Point(lon, lat) for lon, lat in lonlat]
    failed = [mi + 1 for mi in range(12)
              if not _sample_month(cat, year, mi, lonlat, pt_geoms, cube, aoi)]
    return cube.transpose(1, 0, 2).reshape(n, 72), failed  # month-major, matching the S2 cube


def _year_features(cat: StacClient, year: int, lonlat: np.ndarray, aoi: BBox,
                   cache: Path) -> np.ndarray:
    """Point-sampled Landsat features for one year, cached — but never a partial (failed) fetch."""
    if cache.exists():
        logger.info("loaded cached %d features", year)
        return np.load(cache)["feats"]
    feats, failed = sample_year(cat, year, lonlat, aoi)
    if failed:
        logger.warning("  %d: transient-failed months %s — NOT caching; rerun to fill", year, failed)
    else:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, feats=feats)
    return feats


def _load_species_points(csv: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CSU points → (lonlat (N,2), per-point species label, trip groups) inside the San Juan AOI.

    Labels are kept per-taxon (not pooled to invasive/native) so C1 can score tamarisk-vs-native and
    Russian-olive-vs-native separately — RO is the beetle-negative control that must NOT invert.
    """
    keep = INVASIVE | NATIVE
    pts = [p for p in csu_points.load_points(csv, bbox=SJ_AOI) if p.label in keep]
    if not pts:
        raise ValueError("no invasive/native CSU points in the San Juan AOI — check the CSV path")
    lonlat = np.array([[p.lon, p.lat] for p in pts])
    labels = np.array([p.label for p in pts])
    trips = np.array([p.trip for p in pts])
    logger.info("species points: %d over %d field trips — %s", len(pts), len(set(trips)),
                {lab: int((labels == lab).sum()) for lab in sorted(keep)})
    return lonlat, labels, trips


def _impute_with(x: np.ndarray, med: np.ndarray) -> np.ndarray:
    """Fill NaNs in ``x`` with the pre-fitted per-column medians ``med`` (fitted on train rows only)."""
    return np.where(np.isfinite(x), x, med)


def beetle_cv(feats_by_year: dict[int, np.ndarray], y: np.ndarray,
              trips: np.ndarray) -> dict[int, float]:
    """Out-of-fold AUROC per year from a ``TRAIN_YEAR``-trained RF, over the same trip-grouped folds.

    Every fold trains on ``TRAIN_YEAR`` features and predicts held-out points' features in *each*
    year, so the per-year AUROCs differ only by the year sampled — the train-year→pre-beetle gap
    (and sign) is the beetle, with space and the fold split held common (the 3B isolation, cross-era).
    """
    n = len(y)
    n_splits = min(CV_SPLITS, len(set(trips)))
    gkf = GroupKFold(n_splits=n_splits)
    oof = {yr: np.full(n, np.nan, np.float64) for yr in feats_by_year}
    train_feats = feats_by_year[TRAIN_YEAR]
    for tr, te in gkf.split(train_feats, y, groups=trips):
        # Fit imputation medians on the TRAIN rows only — a full-array median would leak held-out
        # (and other-year) values into the fill applied to test rows.
        med = np.nanmedian(train_feats[tr], axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        rf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                    max_features="sqrt", n_jobs=-1, random_state=0)
        rf.fit(_impute_with(train_feats[tr], med), y[tr])
        for yr, feats in feats_by_year.items():
            oof[yr][te] = rf.predict_proba(_impute_with(feats[te], med))[:, 1]
    return {yr: validate_layer.auc(p[y == 1], p[y == 0]) for yr, p in oof.items()}


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=csu_points.CSU_POINTS_CSV_URL,
                    help="CSU TabletData_2017.csv (local path or the default CC BY-SA URL)")
    ap.add_argument("--years", type=int, nargs="+", default=[TRAIN_YEAR, 2015, 2000],
                    help=f"years to sample; {TRAIN_YEAR} is the training year, earlier years test the beetle")
    ap.add_argument("--cache", type=Path, default=HERE / ".tmp/phase3c",
                    help="per-year point-sample cache dir")
    return ap


def _report(taxon: str, scores: dict[int, float], is_control: bool) -> None:
    """Log the separability gate + beetle deltas for one taxon-vs-native classification."""
    role = "beetle-negative CONTROL — should NOT invert" if is_control else "beetle signal taxon"
    logger.info("")
    logger.info("═══ Phase 3C — %s-vs-native across the beetle era (%s) ═══", taxon, role)
    logger.info("  Test A — in-domain separability   %d AUROC = %.3f  (gate: ≥ %.2f)",
                TRAIN_YEAR, scores[TRAIN_YEAR], SEPARABILITY_GATE)
    for yr in sorted((yr for yr in scores if yr != TRAIN_YEAR), reverse=True):
        tag = "PRE-beetle" if yr < 2004 else "post-beetle"
        flip = "  ⚠ INVERTED (<0.5)" if scores[yr] < 0.5 else ""
        # ~0.05 of any drop is the Landsat-5→8 sensor change (3A control); an inversion is not.
        logger.info("  Test C1 — %s %d AUROC = %.3f  (Δ from %d = %+.3f; ≈0.05 of a drop is sensor)%s",
                    tag, yr, scores[yr], TRAIN_YEAR, scores[yr] - scores[TRAIN_YEAR], flip)


def _score_taxon(taxon: str, labels: np.ndarray, native: np.ndarray,
                 feats_by_year: dict[int, np.ndarray], trips: np.ndarray) -> bool:
    """Run + report Test A/C1 for one taxon vs native. Returns True iff its separability gate FAILED."""
    is_taxon = labels == taxon
    mask = native | is_taxon
    n_pos, n_neg = int(is_taxon.sum()), int(native.sum())
    if n_pos < MIN_TAXON or n_neg < MIN_TAXON:
        logger.warning("skip %s-vs-native — too few points (%d vs %d native, need ≥ %d each)",
                       taxon, n_pos, n_neg, MIN_TAXON)
        return False
    sub = {yr: f[mask] for yr, f in feats_by_year.items()}
    scores = beetle_cv(sub, is_taxon[mask].astype(int), trips[mask])
    is_control = taxon == csu_points.RUSSIAN_OLIVE
    _report(taxon, scores, is_control)
    gate = scores[TRAIN_YEAR]
    if not is_control and (not np.isfinite(gate) or gate < SEPARABILITY_GATE):
        logger.error("Test A gate FAILED for %s (AUROC %.3f < %.2f) — ABORT.",
                     taxon, gate, SEPARABILITY_GATE)
        return True
    return False


def main() -> int:
    a = _build_parser().parse_args()
    if TRAIN_YEAR not in a.years:
        raise SystemExit(f"--years must include the training year {TRAIN_YEAR}")

    lonlat, labels, trips = _load_species_points(a.csv)
    aoi = (float(lonlat[:, 0].min()) - 0.05, float(lonlat[:, 1].min()) - 0.05,
           float(lonlat[:, 0].max()) + 0.05, float(lonlat[:, 1].max()) + 0.05)
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)

    feats_by_year = {yr: _year_features(cat, yr, lonlat, aoi, a.cache / f"landsat_{yr}_pts.npz")
                     for yr in sorted(a.years, reverse=True)}
    native = labels == csu_points.NATIVE_RIPARIAN_WOODY
    # Score each invasive taxon vs native separately — Russian olive is the beetle-negative control.
    # Both always run (no short-circuit) so each reports; abort the run if any signal gate fails.
    aborted = False
    for taxon in (csu_points.TAMARISK, csu_points.RUSSIAN_OLIVE):
        if _score_taxon(taxon, labels, native, feats_by_year, trips):
            aborted = True
    return 1 if aborted else 0


if __name__ == "__main__":
    raise SystemExit(main())
