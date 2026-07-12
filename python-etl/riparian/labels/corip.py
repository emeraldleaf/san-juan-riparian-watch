"""CO-RIP → confidence-weighted riparian-extent labels for **Colorado**.

The label source for the ground NMRipMap does not cover. NMRipMap is **New Mexico only**, which is
why the Turkey Creek (CO) tile still runs on weak labels and scores ~0.00 F1 on the ag valley.

    Woodward, B., Evangelista, P., Vorster, A., et al. (2018). "CO-RIP: A Riparian Vegetation and
    Corridor Extent Dataset for Colorado River Basin Streams and Rivers." *ISPRS Int. J. Geo-Inf.*
    7(10):397. Data: https://doi.org/10.5061/dryad.3g55sv8 (1.25 GB)

Products: a riparian vegetation raster (``0`` absence / ``100`` presence) and valley-bottom polygons,
covering the entire Colorado River Basin, per EPA Level III ecoregion.

**Vintage: 2006 and 2016.** Determined from the source team's own report (Evangelista et al. 2018,
§Goal 1) because the Dryad landing page never states it and the README is behind an auth token:

    "We used **Landsat** cloud free growing season composites ... we developed random forest models
     of riparian vegetation for each ecoregion in **2006 and 2016** ... a continuous riparian
     vegetation map for the Colorado River Basin for each year ... at a **30 m** resolution."

So: **fit against 2016 imagery** (or 2006, matching whichever raster is loaded). Fitting CO-RIP
labels to 2024 reflectance is the same self-inflicted error we already made once with NMRipMap.

## 🔴 CO-RIP is WEAKEST exactly where we need it

This is the load-bearing caveat, and it is in the authors' own words:

    "Models performed well, overall, with **Out of bag (OOB) errors ranging from 2% - 35%, depending
     on the ecoregion** ... **ecoregions further north and encompassing mountainous regions had lower
     accuracy** than those further south in less mountainous and arid environments."

    "**our map may likely over predict riparian vegetation in high elevation environments**"

**Turkey Creek is northern, mountainous, high-elevation Southern Rockies** — the ecoregion class where
CO-RIP is least accurate *and* biased toward over-prediction. The tile we most want CO-RIP for is the
tile CO-RIP is worst at.

Therefore CO-RIP is **not ground truth here**. It is a confidence-weighted weak label, per
``docs/decisions/2026-07-11-confidence-weighted-label-crosswalk.md``: *"No source is ground truth.
Every label carries a source, a class, and a confidence."* The confidence is not decoration — for a
high-elevation tile it is the difference between a usable prior and a systematically inflated one.

Also note the authors' own warning about their change product, which bears directly on our Stage 3:

    "Change maps should be interpreted cautiously, as changes shown may reflect actual change, or
     they may be due to **model errors when comparing the two years**."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

CORIP_DOI: Final[str] = "https://doi.org/10.5061/dryad.3g55sv8"

LABEL_YEARS: Final[tuple[int, int]] = (2006, 2016)
"""The two epochs CO-RIP models. **Fit against imagery from the year you load.** See CLAUDE.md."""

RESOLUTION_M: Final[int] = 30
"""Landsat. Coarse against a narrow corridor — a known limit, not a surprise."""

PRESENCE: Final[int] = 100
ABSENCE: Final[int] = 0

SOURCE: Final[str] = "corip"

# --- Confidence by ecoregion ---------------------------------------------------------------
#
# The authors report OOB error 2%-35% BY ECOREGION, with the north/mountainous end worst and an
# explicit over-prediction bias at high elevation. Encoding a single basin-wide confidence would
# throw away the one thing they told us that matters most for OUR tiles.
#
# Confidence = 1 - OOB_error, banded conservatively. These are deliberately pessimistic where the
# authors flagged trouble: an over-predicting label is worse than a missing one, because it teaches
# the model that upland IS riparian — the exact failure the NMRipMap crosswalk was built to stop.
ECOREGION_CONFIDENCE: Final[dict[str, float]] = {
    # Arid / southern / low-relief — where CO-RIP is strongest (OOB ~2-10%)
    "sonoran_basin": 0.95,
    "mojave_basin": 0.95,
    "chihuahuan_desert": 0.92,
    "colorado_plateau": 0.85,      # our Animas/Malpais band; mid-range
    "arizona_new_mexico_plateau": 0.85,
    # Northern / mountainous / high elevation — where CO-RIP is WEAKEST and over-predicts
    "southern_rockies": 0.55,      # <- TURKEY CREEK. Lowest confidence for a reason.
    "wasatch_uinta_mountains": 0.55,
    "middle_rockies": 0.55,
    "arizona_new_mexico_mountains": 0.60,
}
DEFAULT_CONFIDENCE: Final[float] = 0.65
"""Used when the ecoregion is unknown. Deliberately below the arid-region values."""

HIGH_ELEVATION_ECOREGIONS: Final[frozenset[str]] = frozenset({
    "southern_rockies", "wasatch_uinta_mountains", "middle_rockies",
    "arizona_new_mexico_mountains",
})
"""Where the authors say the map "may likely over predict riparian vegetation"."""


@dataclass(frozen=True)
class CoRipLabel:
    """One CO-RIP-derived label, carrying its provenance and its confidence."""

    is_riparian: bool
    year: int
    ecoregion: str
    confidence: float
    source: str = SOURCE

    @property
    def over_prediction_risk(self) -> bool:
        """True where the authors warn the map over-predicts riparian vegetation."""
        return self.ecoregion in HIGH_ELEVATION_ECOREGIONS


def confidence_for(ecoregion: str) -> float:
    """Confidence for a CO-RIP label in a given EPA Level III ecoregion.

    Not a formality. CO-RIP's OOB error spans **2%–35% by ecoregion**, and it over-predicts at high
    elevation — so a single blended number would be misleading exactly where we need it (Turkey Creek
    is Southern Rockies). Unknown ecoregions get a conservative default rather than an optimistic one.
    """
    key = ecoregion.strip().lower().replace(" ", "_").replace("-", "_")
    conf = ECOREGION_CONFIDENCE.get(key)
    if conf is None:
        logger.warning(
            "unknown ecoregion %r — using the conservative default %.2f. Add it to "
            "ECOREGION_CONFIDENCE rather than letting it inherit a guess.",
            ecoregion, DEFAULT_CONFIDENCE,
        )
        return DEFAULT_CONFIDENCE
    return conf


def label_from_pixel(value: int, year: int, ecoregion: str) -> CoRipLabel | None:
    """Map a CO-RIP raster pixel (``0`` / ``100``) to a confidence-weighted label.

    Returns None for any value that is neither presence nor absence — CO-RIP's raster is binary, so
    anything else is nodata or corruption, and guessing at it is how ~45% of a label set goes wrong.
    """
    if year not in LABEL_YEARS:
        raise ValueError(f"CO-RIP models {LABEL_YEARS}, not {year} — fit against the label's year")
    if value == PRESENCE:
        is_riparian = True
    elif value == ABSENCE:
        is_riparian = False
    else:
        return None
    return CoRipLabel(
        is_riparian=is_riparian, year=year, ecoregion=ecoregion,
        confidence=confidence_for(ecoregion),
    )


def download_instructions() -> str:
    """CO-RIP cannot be fetched programmatically — Dryad requires a bearer token.

    Returned rather than raised so the caller can surface it, because "the download 403'd" is a far
    worse failure mode than "here is exactly what to do".
    """
    return (
        f"CO-RIP must be downloaded by hand (Dryad blocks automated fetches):\n"
        f"  1. Open {CORIP_DOI}\n"
        f"  2. Download CORIP_Riparian_Corridor_Vegetation.zip (1.25 GB)\n"
        f"  3. Unzip to data/reference/corip/\n"
        f"  4. Note WHICH YEAR's raster you use — {LABEL_YEARS[0]} or {LABEL_YEARS[1]} — and fit "
        f"against imagery from that year.\n"
        f"  Turkey Creek is Southern Rockies: confidence "
        f"{ECOREGION_CONFIDENCE['southern_rockies']}, and the authors warn the map OVER-PREDICTS "
        f"riparian vegetation at high elevation. Do not treat it as ground truth."
    )
