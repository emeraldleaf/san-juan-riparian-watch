"""SMP-aligned composite riparian health scorer.

Computes a composite score per riparian buffer using the Colorado Stream
Management Program's **80/10/10** weighting model:

  - 80% Vegetation Structure (7 sub-metrics, each 0–10)
  - 10% Habitat Connectivity (NLCD continuity along corridor)
  - 10% Contributing Area (natural vs developed in wider zone)

Grades: A (≥80), B (60–79), C (40–59), D (20–39), F (<20)

This module reads from silver/gold tables and writes to
gold.buffer_health_score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

# Category weights (must sum to 1.0)
WEIGHT_VEGETATION = 0.80
WEIGHT_CONNECTIVITY = 0.10
WEIGHT_CONTRIBUTING = 0.10

# Grade thresholds
GRADE_THRESHOLDS = [
    (80, "A"),
    (60, "B"),
    (40, "C"),
    (20, "D"),
    (0, "F"),
]

# NDVI thresholds for scoring (peak-growing season)
NDVI_EXCELLENT = 0.60   # score 10
NDVI_GOOD = 0.45        # score 7.5
NDVI_MODERATE = 0.30    # score 5
NDVI_POOR = 0.15        # score 2.5
# below POOR → score 0

# NLCD classes considered "natural" for contributing area analysis
NATURAL_NLCD_CLASSES = {
    41, 42, 43,  # Forest
    51, 52,      # Shrubland
    71, 72, 73, 74,  # Grassland/Herbaceous
    90, 95,      # Wetlands
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BufferScore:
    """Complete health score for a single buffer."""

    buffer_id: int

    # Vegetation sub-scores (0–10)
    ndvi_score: float
    vertical_complexity_score: float
    species_composition_score: float
    shrub_layer_score: float
    patchiness_score: float
    native_regeneration_score: float
    native_cover_score: float

    # Category scores (0–100)
    vegetation_structure_score: float
    connectivity_score: float
    contributing_area_score: float

    # Composite
    composite_score: float
    score_grade: str


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def score_ndvi(mean_ndvi: float | None) -> float:
    """Score NDVI health on a 0–10 scale.

    Uses peak-growing-season NDVI thresholds calibrated for
    semi-arid riparian systems in the San Juan Basin.
    """
    if mean_ndvi is None:
        return 5.0  # neutral if no data

    if mean_ndvi >= NDVI_EXCELLENT:
        return 10.0
    if mean_ndvi >= NDVI_GOOD:
        return 7.5 + 2.5 * (mean_ndvi - NDVI_GOOD) / (NDVI_EXCELLENT - NDVI_GOOD)
    if mean_ndvi >= NDVI_MODERATE:
        return 5.0 + 2.5 * (mean_ndvi - NDVI_MODERATE) / (NDVI_GOOD - NDVI_MODERATE)
    if mean_ndvi >= NDVI_POOR:
        # POOR anchors at 2.5 and rises to 5.0 at MODERATE, so the piecewise curve is
        # continuous (was 0..2.5, which then jumped to 5.0 at MODERATE).
        return 2.5 + 2.5 * (mean_ndvi - NDVI_POOR) / (NDVI_MODERATE - NDVI_POOR)
    return 0.0


def score_vertical_complexity(
    evh_heights: list[float],
    evt_lifeforms: list[str],
) -> float:
    """Score vertical complexity from LANDFIRE EVH heights.

    Multi-storied canopy (tree + shrub + herb layers) scores high.
    Monotypic or bare scores low.
    """
    if not evh_heights:
        return 5.0

    # Count distinct vertical strata
    strata = set()
    for h, lf in zip(evh_heights, evt_lifeforms):
        if lf == "Tree" and h > 5:
            strata.add("canopy")
        elif lf == "Shrub" or (lf == "Tree" and h <= 5):
            strata.add("understory")
        elif lf == "Herb":
            strata.add("ground")

    strata_count = len(strata)
    max_height = max(evh_heights) if evh_heights else 0

    # Score: 3 strata=10, 2=7, 1=4, 0=1
    strata_score = min(10, strata_count * 3 + 1)

    # Height bonus (tall canopy = good riparian)
    height_bonus = min(2.0, max_height / 10.0)

    return min(10.0, strata_score + height_bonus)


def score_species_composition(
    evt_codes: list[int],
    notable_codes: set[int] | None = None,
) -> float:
    """Score species composition from LANDFIRE EVT codes.

    Higher diversity and presence of riparian-obligate species score better.
    """
    if not evt_codes:
        return 5.0

    unique_types = len(set(evt_codes))
    # More diversity = better; diminishing returns above 5 types
    diversity_score = min(10.0, unique_types * 2.0)

    # Bonus for known San Juan Basin riparian codes
    if notable_codes:
        riparian_present = any(c in notable_codes for c in evt_codes)
        if riparian_present:
            diversity_score = min(10.0, diversity_score + 2.0)

    return diversity_score


def score_shrub_layer(
    lifeforms: list[str],
    area_pcts: list[float],
) -> float:
    """Score shrub layer presence from LANDFIRE EVT.

    Healthy riparian zones have 20-60% shrub cover.
    """
    if not lifeforms:
        return 5.0

    shrub_pct = sum(
        pct for lf, pct in zip(lifeforms, area_pcts)
        if lf == "Shrub"
    )

    # Optimal range: 20-60%
    if 20 <= shrub_pct <= 60:
        return 10.0
    if 10 <= shrub_pct < 20:
        return 6.0 + 4.0 * (shrub_pct - 10) / 10
    if 60 < shrub_pct <= 80:
        return 6.0 + 4.0 * (80 - shrub_pct) / 20
    if shrub_pct < 10:
        return max(0, shrub_pct * 0.6)
    return max(0, (100 - shrub_pct) * 0.3)


def score_patchiness(nlcd_classes: list[int], area_pcts: list[float]) -> float:
    """Score landscape patchiness from NLCD classes.

    Diverse mix of natural cover types with no single dominant class
    indicates healthy mosaic.  High fragmentation with developed patches
    scores low.
    """
    if not nlcd_classes:
        return 5.0

    natural_classes = [
        (c, p) for c, p in zip(nlcd_classes, area_pcts)
        if c in NATURAL_NLCD_CLASSES
    ]

    if not natural_classes:
        return 0.0

    n_natural_types = len({c for c, _ in natural_classes})


    # Diversity of natural types (max ~5)
    diversity = min(10.0, n_natural_types * 2.0)
    # Penalty if any single class dominates (>80%)
    max_pct = max(p for _, p in natural_classes) if natural_classes else 0
    evenness = 10.0 if max_pct < 60 else 10.0 * (100 - max_pct) / 40

    return min(10.0, (diversity + evenness) / 2)


def score_native_cover(
    nlcd_classes: list[int],
    area_pcts: list[float],
) -> float:
    """Score native (natural) land cover percentage.

    Higher natural cover = better. Developed/agriculture = lower.
    """
    if not nlcd_classes:
        return 5.0

    natural_pct = sum(
        p for c, p in zip(nlcd_classes, area_pcts)
        if c in NATURAL_NLCD_CLASSES
    )

    # Linear scale: 100% natural = 10, 0% = 0
    return min(10.0, natural_pct / 10.0)


def score_native_regeneration(ndvi_trend: float | None) -> float:
    """Score regeneration potential from NDVI temporal trend.

    Positive trend suggests recovery; negative suggests decline.
    If no trend data, default to neutral.
    """
    if ndvi_trend is None:
        return 5.0

    # Positive trend up to +0.05/year → score 10
    if ndvi_trend >= 0.05:
        return 10.0
    if ndvi_trend >= 0:
        return 5.0 + 5.0 * ndvi_trend / 0.05
    # Negative trend down to -0.05 → score 0
    if ndvi_trend >= -0.05:
        return 5.0 + 5.0 * ndvi_trend / 0.05
    return 0.0


def score_connectivity(
    _buffer_id: int,
    adjacent_natural_pcts: list[float],
) -> float:
    """Score habitat connectivity based on NLCD cover in adjacent buffers.

    Continuous natural cover along the corridor = high score.
    Gaps indicate fragmentation.
    """
    if not adjacent_natural_pcts:
        return 50.0  # no adjacency data → neutral

    avg_natural = sum(adjacent_natural_pcts) / len(adjacent_natural_pcts)
    # Scale: 100% natural corridor = 100, 0% = 0
    return min(100.0, avg_natural)


def score_contributing_area(
    nlcd_classes: list[int],
    area_pcts: list[float],
) -> float:
    """Score the contributing (surrounding) area from NLCD.

    Natural land use in the wider watershed area around the buffer
    indicates less anthropogenic disturbance.

    Returns score on 0–100 scale.
    """
    if not nlcd_classes:
        return 50.0

    natural_pct = sum(
        p for c, p in zip(nlcd_classes, area_pcts)
        if c in NATURAL_NLCD_CLASSES
    )

    return min(100.0, natural_pct)


def compute_composite(
    vegetation_structure: float,
    connectivity: float,
    contributing_area: float,
) -> float:
    """Compute the 80/10/10 composite score.

    Args:
        vegetation_structure: 0–100 scale.
        connectivity: 0–100 scale.
        contributing_area: 0–100 scale.

    Returns:
        Composite score on 0–100 scale.
    """
    return (
        WEIGHT_VEGETATION * vegetation_structure
        + WEIGHT_CONNECTIVITY * connectivity
        + WEIGHT_CONTRIBUTING * contributing_area
    )


def assign_grade(score: float) -> str:
    """Assign A–F letter grade from composite score."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class HealthScorer:
    """Computes SMP composite health scores for all riparian buffers.

    Reads silver-layer data (vegetation_health, buffer_land_cover,
    buffer_vegetation_structure, buffer_soils) and writes results
    to gold.buffer_health_score.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def score_all_buffers(self) -> int:
        """Compute and persist health scores for every riparian buffer.

        Returns:
            Number of buffers scored.
        """
        logger.info("Computing composite health scores for all buffers")

        # Gather per-buffer data
        buffers = self._get_buffer_ids()
        ndvi_data = self._get_ndvi_data()
        landcover_data = self._get_landcover_data()
        vegetation_data = self._get_vegetation_data()

        # Clear previous scores
        with self._engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE gold.buffer_health_score"))
            conn.commit()

        scores: list[BufferScore] = []
        for buffer_id in buffers:
            score = self._score_buffer(
                buffer_id, ndvi_data, landcover_data, vegetation_data,
            )
            scores.append(score)

        # Batch insert
        if scores:
            self._write_scores(scores)

        logger.info("Scored %d buffers", len(scores))
        return len(scores)

    def update_summary(self) -> None:
        """Update gold.riparian_summary with aggregate composite scores."""
        logger.info("Updating riparian summary with composite score aggregates")

        # Aggregate composite scores PER WATERSHED and correlate on watershed_id.
        # Buffers link to a watershed by the same spatial intersection used in
        # calculate_summary (b.geom && w.geom AND ST_Intersects). A single
        # basin-wide aggregate cross-joined onto every summary row would give every
        # watershed identical numbers once the study area spans more than one HUC.
        sql = text("""
            UPDATE gold.riparian_summary rs
            SET
                avg_composite_score = sub.avg_score,
                grade_a_pct = sub.a_pct,
                grade_b_pct = sub.b_pct,
                grade_c_pct = sub.c_pct,
                grade_d_pct = sub.d_pct,
                grade_f_pct = sub.f_pct
            FROM (
                SELECT
                    w.id AS watershed_id,
                    AVG(hs.composite_score) AS avg_score,
                    100.0 * COUNT(*) FILTER (WHERE hs.score_grade = 'A')
                        / NULLIF(COUNT(*), 0) AS a_pct,
                    100.0 * COUNT(*) FILTER (WHERE hs.score_grade = 'B')
                        / NULLIF(COUNT(*), 0) AS b_pct,
                    100.0 * COUNT(*) FILTER (WHERE hs.score_grade = 'C')
                        / NULLIF(COUNT(*), 0) AS c_pct,
                    100.0 * COUNT(*) FILTER (WHERE hs.score_grade = 'D')
                        / NULLIF(COUNT(*), 0) AS d_pct,
                    100.0 * COUNT(*) FILTER (WHERE hs.score_grade = 'F')
                        / NULLIF(COUNT(*), 0) AS f_pct
                FROM bronze.watersheds w
                JOIN silver.riparian_buffers b
                    ON b.geom && w.geom AND ST_Intersects(b.geom, w.geom)
                JOIN gold.buffer_health_score hs ON hs.buffer_id = b.id
                GROUP BY w.id
            ) sub
            WHERE rs.watershed_id = sub.watershed_id
        """)

        with self._engine.connect() as conn:
            result = conn.execute(sql)
            conn.commit()
            logger.info("Updated %d summary rows with composite scores", result.rowcount)

    # -- Private helpers ----------------------------------------------------

    def _get_buffer_ids(self) -> list[int]:
        """Get all buffer IDs."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id FROM silver.riparian_buffers ORDER BY id")
            ).fetchall()
        return [r[0] for r in rows]

    def _get_ndvi_data(self) -> dict[int, float]:
        """Get latest peak-season NDVI per buffer."""
        sql = text("""
            SELECT DISTINCT ON (buffer_id)
                buffer_id, mean_ndvi
            FROM silver.vegetation_health
            WHERE season_context = 'peak_growing'
            ORDER BY buffer_id, acquisition_date DESC
        """)
        with self._engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return {r[0]: float(r[1]) if r[1] is not None else None for r in rows}

    def _get_landcover_data(self) -> dict[int, list[tuple[int, float, bool]]]:
        """Get NLCD land cover per buffer: {buffer_id: [(class, pct, natural), ...]}"""
        sql = text("""
            SELECT buffer_id, nlcd_class, area_pct, is_natural
            FROM silver.buffer_land_cover
            ORDER BY buffer_id, area_pct DESC
        """)
        result: dict[int, list[tuple[int, float, bool]]] = {}
        with self._engine.connect() as conn:
            for row in conn.execute(sql):
                bid = row[0]
                result.setdefault(bid, []).append((
                    int(row[1]),
                    float(row[2]) if row[2] is not None else 0.0,
                    bool(row[3]),
                ))
        return result

    def _get_vegetation_data(
        self,
    ) -> dict[int, list[tuple[int | None, str | None, str | None, float | None, float | None]]]:
        """Get LANDFIRE vegetation per buffer:
        {buffer_id: [(evt_code, evt_name, dominant_lifeform, mean_height, area_pct), ...]}
        """
        sql = text("""
            SELECT buffer_id, evt_code, evt_name, dominant_lifeform,
                   mean_height_m, area_pct
            FROM silver.buffer_vegetation_structure
            ORDER BY buffer_id, area_pct DESC
        """)
        result: dict[int, list[tuple]] = {}
        with self._engine.connect() as conn:
            for row in conn.execute(sql):
                bid = row[0]
                result.setdefault(bid, []).append((
                    int(row[1]) if row[1] is not None else None,
                    row[2],
                    row[3],
                    float(row[4]) if row[4] is not None else None,
                    float(row[5]) if row[5] is not None else 0.0,
                ))
        return result

    def _score_buffer(
        self,
        buffer_id: int,
        ndvi_data: dict[int, float | None],
        landcover_data: dict[int, list[tuple[int, float, bool]]],
        vegetation_data: dict[int, list[tuple]],
    ) -> BufferScore:
        """Score a single buffer using all available data."""

        # -- NDVI sub-score --
        mean_ndvi = ndvi_data.get(buffer_id)
        ndvi_sc = score_ndvi(mean_ndvi)

        # -- LANDFIRE sub-scores --
        veg = vegetation_data.get(buffer_id, [])
        # Vertical complexity zips (height, lifeform) pairwise, so both lists must be
        # filtered TOGETHER — filtering only heights misaligns every pair once any row
        # has a NULL height.
        veg_with_height = [v for v in veg if v[3] is not None]
        heights = [v[3] for v in veg_with_height]
        height_lifeforms = [v[2] or "Unknown" for v in veg_with_height]
        # Shrub layer zips (lifeform, area_pct) over all rows — keep those aligned.
        lifeforms = [v[2] or "Unknown" for v in veg]
        area_pcts_veg = [v[4] for v in veg]
        evt_codes = [v[0] for v in veg if v[0] is not None]

        vert_sc = score_vertical_complexity(heights, height_lifeforms)
        species_sc = score_species_composition(evt_codes)
        shrub_sc = score_shrub_layer(lifeforms, area_pcts_veg)

        # -- NLCD sub-scores --
        lc = landcover_data.get(buffer_id, [])
        nlcd_classes = [c for c, _, _ in lc]
        nlcd_pcts = [p for _, p, _ in lc]

        patch_sc = score_patchiness(nlcd_classes, nlcd_pcts)
        native_sc = score_native_cover(nlcd_classes, nlcd_pcts)

        # -- Regeneration (no multi-date trend yet → neutral) --
        regen_sc = score_native_regeneration(None)

        # -- Vegetation structure composite (average of 7 sub-scores, scaled to 0–100) --
        sub_scores = [
            ndvi_sc, vert_sc, species_sc, shrub_sc,
            patch_sc, regen_sc, native_sc,
        ]
        veg_structure = (sum(sub_scores) / len(sub_scores)) * 10.0  # 0–10 avg → 0–100

        # -- Connectivity (simple: use this buffer's natural % as proxy) --
        connect_sc = score_connectivity(buffer_id, [native_sc * 10.0])

        # -- Contributing area (use NLCD natural percentage) --
        contrib_sc = score_contributing_area(nlcd_classes, nlcd_pcts)

        # -- Composite --
        composite = compute_composite(veg_structure, connect_sc, contrib_sc)
        grade = assign_grade(composite)

        return BufferScore(
            buffer_id=buffer_id,
            ndvi_score=round(ndvi_sc, 2),
            vertical_complexity_score=round(vert_sc, 2),
            species_composition_score=round(species_sc, 2),
            shrub_layer_score=round(shrub_sc, 2),
            patchiness_score=round(patch_sc, 2),
            native_regeneration_score=round(regen_sc, 2),
            native_cover_score=round(native_sc, 2),
            vegetation_structure_score=round(veg_structure, 2),
            connectivity_score=round(connect_sc, 2),
            contributing_area_score=round(contrib_sc, 2),
            composite_score=round(composite, 2),
            score_grade=grade,
        )

    def _write_scores(self, scores: list[BufferScore]) -> None:
        """Batch-insert scores into gold.buffer_health_score."""
        sql = text("""
            INSERT INTO gold.buffer_health_score (
                buffer_id,
                ndvi_score, vertical_complexity_score, species_composition_score,
                shrub_layer_score, patchiness_score, native_regeneration_score,
                native_cover_score,
                vegetation_structure_score, connectivity_score,
                contributing_area_score,
                composite_score, score_grade
            ) VALUES (
                :buffer_id,
                :ndvi_score, :vertical_complexity_score, :species_composition_score,
                :shrub_layer_score, :patchiness_score, :native_regeneration_score,
                :native_cover_score,
                :vegetation_structure_score, :connectivity_score,
                :contributing_area_score,
                :composite_score, :score_grade
            )
        """)

        with self._engine.connect() as conn:
            for s in scores:
                conn.execute(sql, {
                    "buffer_id": s.buffer_id,
                    "ndvi_score": s.ndvi_score,
                    "vertical_complexity_score": s.vertical_complexity_score,
                    "species_composition_score": s.species_composition_score,
                    "shrub_layer_score": s.shrub_layer_score,
                    "patchiness_score": s.patchiness_score,
                    "native_regeneration_score": s.native_regeneration_score,
                    "native_cover_score": s.native_cover_score,
                    "vegetation_structure_score": s.vegetation_structure_score,
                    "connectivity_score": s.connectivity_score,
                    "contributing_area_score": s.contributing_area_score,
                    "composite_score": s.composite_score,
                    "score_grade": s.score_grade,
                })
            conn.commit()

        logger.info("Wrote %d health scores to gold.buffer_health_score", len(scores))
