"""CSU/NREL field points → normalized invasive-species labels, with defoliation as a STATE.

The label source that makes a beetle-aware Stage 2 possible at all.

    Vorster, A., Evangelista, P., West, A., et al. (2018). "Tamarisk and Russian Olive Occurrence
    and Absence Dataset Collected in Select Tributaries of the Colorado River for 2017."
    *Data* 3(4):42. https://doi.org/10.3390/data3040042
    Data: https://mountainscholar.org/items/220da1b3-cacb-426b-9938-793d1fe7aa5b

Why this exists — three things NMRipMap **cannot** give us:

1. **Defoliation as a first-class state.** The source records tamarisk as *live*, *dead*, a
   *live/dead mix*, or **"red tam"** — red foliage from tamarisk-beetle attack. 547 of the 3,491
   records are beetle-affected. Our claim that defoliation must be modelled as a *state* rather than
   as *absence* had **no labels at all** before this dataset.
2. **Tamarisk vs Russian olive, separated.** NMRipMap's `IC` class ("Lowland Introduced Riparian
   Woodland and Scrub") **conflates the two species and cannot split them**. This can: 191 Russian-olive
   records, distinct from tamarisk.
3. **Real absences.** ~530 records are water / bare ground / road / agriculture / explicit
   `absent_point`. The RF baseline currently trains against *randomly generated background*, which
   CSU themselves flag as the weaker option.

The crosswalk lives in ``csu_points_crosswalk.csv`` so the mapping is inspectable rather than buried
in a dict — same discipline as ``nmripmap.py``, and for the same reason: the last time a label mapping
was implicit, ~45% of the positive class was wrong.

**Label vintage: 2017.** Fit against 2017 imagery. See CLAUDE.md.

**Licence: CC BY-SA 4.0** (verified from the DSpace `dc.rights.uri`, not from a README). Training on
it is permitted, attribution is mandatory, and **ShareAlike binds our derived data products** — any
label layer or invasive-cover map built from these points must itself be CC BY-SA 4.0. See
``docs/data-licenses.md``. This is not a footnote: plan for it, do not discover it at publication.

Known defects in the SOURCE FILE (both handled here; do not "clean up" the handling):

* **`Virgin_River` has x and y TRANSPOSED** — all 119 rows carry latitude in `x` and longitude in `y`,
  which drops them in the wrong hemisphere. Detected by coordinate range, not by trip name, so a new
  trip with the same defect is caught too.
* **Casing and spelling drift** — ``Russian olive`` / ``Russian Olive``, ``tamarisk`` / ``Tamarisk``,
  ``gamble oak`` / ``gambel oak``, ``grass and Forbes`` (sic). Never trust the raw ``Species`` string.

Geographic caveat, verified by counting — **read this before planning a run**:

* Only **~148** records fall inside the San Juan basin (45 Russian olive, 37 tamarisk). Enough to
  **split the species locally and to validate**; **not** enough to train on alone.
* **Zero `red tam` records are in the San Juan AOI** — all 283 are Arizona/Escalante. A beetle-aware
  model must be trained basin-wide and **transferred**, or the AOI must be widened. This dataset
  cannot locally validate defoliation on our river.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import requests

logger = logging.getLogger(__name__)

CSU_POINTS_CSV_URL: Final[str] = (
    "https://mountainscholar.org/bitstreams/133b91bb-f416-4a18-aac8-1062d7d884dd/download"
)
CROSSWALK_PATH: Final[Path] = Path(__file__).with_name("csu_points_crosswalk.csv")

LABEL_YEAR: Final[int] = 2017
"""Field season. Fit against 2017 imagery — see the module docstring."""

# Normalized classes.
TAMARISK: Final[str] = "tamarisk"
RUSSIAN_OLIVE: Final[str] = "russian_olive"
NATIVE_RIPARIAN_WOODY: Final[str] = "native_riparian_woody"
OTHER_WOODY: Final[str] = "other_woody"
UPLAND_VEG: Final[str] = "upland_veg"
AGRICULTURE: Final[str] = "agriculture"
NON_VEG: Final[str] = "non_veg"
ABSENCE: Final[str] = "absence"

INVASIVE_LABELS: Final[frozenset[str]] = frozenset({TAMARISK, RUSSIAN_OLIVE})

# Tamarisk condition — a STATE, never collapsed to presence/absence. Defoliated tamarisk is
# tamarisk: it is the same plant, browning early because a beetle ate it. Scoring it as absence is
# precisely the error that inverts the senescence discriminator the whole literature relies on.
LIVE: Final[str] = "live"
DEFOLIATED: Final[str] = "defoliated"
MIXED: Final[str] = "mixed"
DEAD: Final[str] = "dead"

BEETLE_AFFECTED: Final[frozenset[str]] = frozenset({DEFOLIATED, MIXED, DEAD})
"""Conditions attributable to biocontrol. `dead` is included: the beetle kills stands outright."""

# Continental-US bounds, used to detect the transposed rows.
_LON_RANGE: Final[tuple[float, float]] = (-125.0, -100.0)
_LAT_RANGE: Final[tuple[float, float]] = (25.0, 45.0)


@dataclass(frozen=True)
class LabeledPoint:
    """One field observation, normalized."""

    lon: float
    lat: float
    label: str
    condition: str | None
    confidence: float
    source_species: str
    trip: str
    plot_id: str

    @property
    def is_invasive(self) -> bool:
        return self.label in INVASIVE_LABELS

    @property
    def is_beetle_affected(self) -> bool:
        """True for defoliated / live-dead-mix / dead tamarisk. **Not** an absence."""
        return self.label == TAMARISK and self.condition in BEETLE_AFFECTED


def load_crosswalk(path: Path = CROSSWALK_PATH) -> dict[str, tuple[str, str | None, float]]:
    """Load ``source_species`` → ``(label, condition, confidence)``.

    Keys are lower-cased and whitespace-collapsed, which is what absorbs the casing drift in the
    source (``Russian olive`` vs ``Russian Olive``).
    """
    out: dict[str, tuple[str, str | None, float]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = _normalize_key(row["source_species"])
            condition = row["tamarisk_condition"].strip() or None
            out[key] = (row["normalized_label"].strip(), condition, float(row["confidence"]))
    return out


def _normalize_key(species: str) -> str:
    return " ".join(species.strip().lower().split())


def fix_coordinates(x: float, y: float) -> tuple[float, float]:
    """Return ``(lon, lat)``, swapping if the row is transposed.

    The ``Virgin_River`` trip carries latitude in ``x`` and longitude in ``y`` for all 119 of its
    rows, which places them in the wrong hemisphere. Detected by RANGE rather than by trip name, so
    the same defect in a different trip is caught rather than trusted.

    Raises:
        ValueError: if neither orientation puts the point in the continental US. Better to fail
            loudly than to silently place a field plot in the ocean.
    """
    if _LON_RANGE[0] <= x <= _LON_RANGE[1] and _LAT_RANGE[0] <= y <= _LAT_RANGE[1]:
        return x, y
    if _LON_RANGE[0] <= y <= _LON_RANGE[1] and _LAT_RANGE[0] <= x <= _LAT_RANGE[1]:
        return y, x  # transposed
    raise ValueError(f"point ({x}, {y}) is not in the continental US in either orientation")


def load_points(
    source: str | Path = CSU_POINTS_CSV_URL,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    timeout: int = 120,
) -> list[LabeledPoint]:
    """Load and normalize the CSU field points.

    Args:
        source: The CSV URL (default) or a local path.
        bbox: Optional ``(minx, miny, maxx, maxy)`` filter in EPSG:4326.
        timeout: HTTP timeout when fetching.

    Returns:
        Normalized points. Rows whose species is not in the crosswalk are **skipped with a warning**
        rather than guessed at — an unmapped label is a crosswalk bug, not a data point.
    """
    crosswalk = load_crosswalk()

    if isinstance(source, Path) or not str(source).startswith(("http://", "https://")):
        text = Path(source).read_text(encoding="utf-8")
    else:
        resp = requests.get(str(source), timeout=timeout)
        resp.raise_for_status()
        text = resp.text

    points: list[LabeledPoint] = []
    unmapped: set[str] = set()
    transposed = 0

    for row in csv.DictReader(text.splitlines()):
        raw = (row.get("Species") or "").strip()
        if not raw:
            continue
        key = _normalize_key(raw)
        if key not in crosswalk:
            unmapped.add(raw)
            continue
        try:
            x, y = float(row["x"]), float(row["y"])
        except (TypeError, ValueError):
            continue
        try:
            lon, lat = fix_coordinates(x, y)
        except ValueError:
            logger.warning("dropping point with unusable coordinates: (%s, %s)", x, y)
            continue
        if (lon, lat) != (x, y):
            transposed += 1
        if bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue

        label, condition, confidence = crosswalk[key]
        points.append(LabeledPoint(
            lon=lon, lat=lat, label=label, condition=condition, confidence=confidence,
            source_species=raw, trip=(row.get("TripName") or "").strip(),
            plot_id=(row.get("PlotID") or "").strip(),
        ))

    if unmapped:
        logger.warning("unmapped species (add to the crosswalk): %s", sorted(unmapped))
    if transposed:
        logger.info("corrected %d transposed coordinate pair(s)", transposed)
    logger.info("CSU points: %d loaded (vintage %d)", len(points), LABEL_YEAR)
    return points


def invasive(points: list[LabeledPoint]) -> list[LabeledPoint]:
    """Tamarisk (any condition) + Russian olive."""
    return [p for p in points if p.is_invasive]


def beetle_affected(points: list[LabeledPoint]) -> list[LabeledPoint]:
    """Defoliated / live-dead-mix / dead tamarisk — the biocontrol training signal."""
    return [p for p in points if p.is_beetle_affected]


# --- Training pool selection -------------------------------------------------------------
#
# The beetle's 2017 impact was NOT uniform across the basin — it was ecoregionally split. Escalante
# (Colorado Plateau, UT) was 21.6% live tamarisk / 31.5% defoliated; Arizona (Sonoran/Mojave, 32-35N)
# was 87% live. Training defoliation on Arizona and applying it to the San Juan is a transfer ACROSS
# an ecoregion boundary — a different desert, a different phenological calendar, and a different stage
# of biocontrol.
#
# That is what CO-RIP warns about (kappa 0.42-0.90 ACROSS its 12 ecoregions), and this project already
# committed to the consequence in STATUS.md: performance is ecoregion-dependent, so results must be
# reported per region. Excluding the lower basin is therefore principled, not convenient.
#
# See docs/decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md.
COLORADO_PLATEAU_TRIPS: Final[frozenset[str]] = frozenset({"Escalante", "SouthWest_CO"})
LOWER_BASIN_TRIPS: Final[frozenset[str]] = frozenset({"Arizona", "Virgin_River"})


def colorado_plateau(points: list[LabeledPoint]) -> list[LabeledPoint]:
    """The ecoregion-matched training pool for the San Juan (lat 36.5-37.8, Colorado Plateau).

    Yields ~1,096 records: 610 invasive, **305 beetle-affected** (117 defoliated / 145 mixed /
    43 dead) — enough to train defoliation as a state.

    Deliberately EXCLUDES Arizona and the Virgin River: different desert, different beetle regime
    (87% of Arizona's tamarisk was still live in 2017). Pooling them would inflate the training set
    by importing exactly the domain shift the model must not learn.
    """
    return [p for p in points if p.trip in COLORADO_PLATEAU_TRIPS]


def negatives(points: list[LabeledPoint]) -> list[LabeledPoint]:
    """Real absences: explicit absence points, non-vegetation, agriculture and upland.

    These replace the randomly generated background the RF baseline uses today — a substitution CSU
    themselves recommend, having relied on random background for the same reason we did (no better
    option existed at the time).
    """
    return [p for p in points if p.label in {ABSENCE, NON_VEG, AGRICULTURE, UPLAND_VEG}]
