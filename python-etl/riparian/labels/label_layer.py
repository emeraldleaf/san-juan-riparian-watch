"""Build the ``label`` vector layer the OlmoEarth fine-tune consumes.

This is Phase 0, step 2 of ``docs/specs/2026-07-12-gpu-finetune-execution-plan.md`` — the
critical path. Every GPU phase is blocked on it, and it is free, so every mistake that can be
found here is a mistake that does not get paid for at $0.43/hr.

The output is a GeoJSON ``FeatureCollection`` carrying integer class ids, matching the scaffold's
``num_classes: 4`` and ``zero_is_invalid: true``:

===  ==========================================================================
id   class
===  ==========================================================================
0    invalid / uncertain — **dropped**, never emitted
1    riparian (woody native + woody introduced + herbaceous)
2    water
3    agriculture
4    other (upland / developed / bare channel)
===  ==========================================================================

**Two things here are load-bearing, and both are about the negatives.**

1. **The negatives must be CORRIDOR negatives.** A model asked to separate riparian from the
   Chihuahuan desert learns "is it green", which is not the task and will not survive contact
   with a dry year. So class 3/4 polygons are clipped to the VBET **valley bottom** — the
   envelope inside which riparian vegetation *can* occur. What is left is the genuinely hard
   negative: corridor land that is not riparian.

2. **The negatives must not swamp the positives.** NMRipMap maps far more non-riparian than
   riparian inside the corridor. Left unbalanced, a segmentation head reaches ~90% accuracy by
   predicting "other" everywhere, and the loss curve looks *healthy* while the model has learned
   nothing. We cap negatives at :data:`MAX_NEGATIVE_RATIO`× positive area and say so in the log.

**Label vintage is 2020** (:data:`LABEL_YEAR`). NMRipMap v2.0 Plus was photo-interpreted from
**NAIP 2020**, so the imagery this layer is fitted against must be 2020 imagery. We have already
made the opposite mistake once — the retracted fair test scored 2020 labels against 2024 imagery
and called the resulting noise a model comparison. Predict any year; **fit on 2020**.

See CLAUDE.md.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from shapely.geometry import shape
from shapely.ops import unary_union

from . import nmripmap
from .nmripmap import PHASE1_CLASS_IDS, LabeledPolygon

logger = logging.getLogger(__name__)

#: The year NMRipMap v2.0 Plus was photo-interpreted from (NAIP 2020). Imagery MUST match it.
LABEL_YEAR: Final[int] = 2020

#: Class ids that are the delineation target.
POSITIVE_CLASS: Final[int] = 1

#: Negatives are capped at this multiple of positive area. Beyond it, a segmentation head scores
#: well by predicting "other" everywhere and the loss curve hides it.
MAX_NEGATIVE_RATIO: Final[float] = 3.0

#: Deterministic sampling. A label layer that changes between runs is not a label layer.
SEED: Final[int] = 20200601


@dataclass(frozen=True)
class LayerStats:
    """What actually went into the layer — logged, and asserted on in tests."""

    n_features: int
    n_positive: int
    n_negative: int
    positive_area_m2: float
    negative_area_m2: float
    dropped_outside_corridor: int

    @property
    def negative_ratio(self) -> float:
        """Negative:positive area ratio. The number that decides whether the head can cheat."""
        if self.positive_area_m2 <= 0:
            return float("inf")
        return self.negative_area_m2 / self.positive_area_m2


def _area_m2(geom) -> float:
    """Approximate area in square metres for a lon/lat geometry.

    A local equal-area projection is overkill for a balance ratio; degrees-squared scaled by the
    latitude cosine is within a few percent across a single basin, and this number only ever feeds
    a ratio.
    """
    import math

    lat = geom.centroid.y
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat))
    return abs(geom.area) * m_per_deg_lat * m_per_deg_lon


def build_extent_labels(
    bbox: tuple[float, float, float, float],
    corridor: object | None = None,
    max_negative_ratio: float = MAX_NEGATIVE_RATIO,
) -> tuple[dict, LayerStats]:
    """Build the extent (Stage-1) label layer for a bbox.

    Args:
        bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4326.
        corridor: A shapely geometry — the VBET valley bottom — that negatives are clipped to.
            ``None`` disables the clip, which is only correct for a test.
        max_negative_ratio: Cap on negative:positive area. See :data:`MAX_NEGATIVE_RATIO`.

    Returns:
        ``(feature_collection, stats)``.

    Raises:
        ValueError: If the fetch yields no riparian polygons at all — an empty positive class is
            never a legitimate label layer, and training on it would "succeed" while learning
            nothing.
    """
    polys = nmripmap.fetch_labeled(bbox)
    return assemble(polys, corridor=corridor, max_negative_ratio=max_negative_ratio)


def assemble(
    polys: list[LabeledPolygon],
    corridor: object | None = None,
    max_negative_ratio: float = MAX_NEGATIVE_RATIO,
) -> tuple[dict, LayerStats]:
    """Assemble labeled polygons into the layer. Split from the fetch so it is testable offline."""
    positives: list[tuple[LabeledPolygon, int]] = []
    negatives: list[tuple[LabeledPolygon, int]] = []

    for p in polys:
        cid = PHASE1_CLASS_IDS.get(p.label, 0)
        if cid == 0:  # invalid / uncertain — never emitted (zero_is_invalid: true)
            continue
        (positives if cid == POSITIVE_CLASS else negatives).append((p, cid))

    if not positives:
        raise ValueError(
            "no riparian (class 1) polygons — refusing to emit a label layer with an empty "
            "positive class. Check the bbox and the L2_Code crosswalk before training on this."
        )

    # 1. Clip negatives to the corridor. A negative outside the valley bottom teaches the model
    #    to separate riparian from desert, which is not the task.
    dropped = 0
    if corridor is not None:
        kept: list[tuple[LabeledPolygon, int]] = []
        for p, cid in negatives:
            geom = p.geometry
            if not geom.intersects(corridor):
                dropped += 1
                continue
            clipped = geom.intersection(corridor)
            if clipped.is_empty:
                dropped += 1
                continue
            kept.append((_with_geometry(p, clipped), cid))
        negatives = kept

    pos_area = sum(_area_m2(p.geometry) for p, _ in positives)

    # 2. Balance. Sample (deterministically) until the negative area is within the cap.
    rng = random.Random(SEED)
    rng.shuffle(negatives)
    budget = pos_area * max_negative_ratio
    balanced: list[tuple[LabeledPolygon, int]] = []
    neg_area = 0.0
    for p, cid in negatives:
        a = _area_m2(p.geometry)
        if neg_area + a > budget:
            continue
        balanced.append((p, cid))
        neg_area += a

    stats = LayerStats(
        n_features=len(positives) + len(balanced),
        n_positive=len(positives),
        n_negative=len(balanced),
        positive_area_m2=pos_area,
        negative_area_m2=neg_area,
        dropped_outside_corridor=dropped,
    )
    _log(stats, n_negative_available=len(negatives))

    features = [_feature(p, cid) for p, cid in positives + balanced]
    return {"type": "FeatureCollection", "features": features}, stats


def _with_geometry(p: LabeledPolygon, geom) -> LabeledPolygon:
    """A copy of ``p`` with a different geometry (LabeledPolygon is frozen)."""
    import dataclasses

    return dataclasses.replace(p, geometry=geom)


def _feature(p: LabeledPolygon, cid: int) -> dict:
    return {
        "type": "Feature",
        "geometry": p.geometry.__geo_interface__,
        "properties": {
            "class": cid,
            "label": p.label,
            "l2_code": p.l2_code,
            "confidence": p.confidence,
            "label_year": LABEL_YEAR,
        },
    }


def _log(stats: LayerStats, n_negative_available: int) -> None:
    logger.info(
        "label layer: %d features (%d riparian, %d negative), negative:positive area = %.2f",
        stats.n_features,
        stats.n_positive,
        stats.n_negative,
        stats.negative_ratio,
    )
    if stats.dropped_outside_corridor:
        logger.info(
            "  dropped %d negatives outside the VBET valley bottom (they were desert, not corridor)",
            stats.dropped_outside_corridor,
        )
    # Never truncate silently. A capped layer that reports nothing reads as "we used everything".
    if n_negative_available > stats.n_negative:
        logger.info(
            "  balance cap dropped %d of %d available negatives (cap = %.1fx positive area)",
            n_negative_available - stats.n_negative,
            n_negative_available,
            MAX_NEGATIVE_RATIO,
        )


def write(fc: dict, dest: Path) -> Path:
    """Write the FeatureCollection to ``dest`` as GeoJSON."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(fc), encoding="utf-8")
    logger.info("wrote %d features -> %s", len(fc["features"]), dest)
    return dest


def corridor_from_vbet(mask: object, transform: object) -> object:
    """Vectorise a VBET valley-bottom mask into one geometry for clipping.

    Args:
        mask: Boolean array from :func:`riparian.delineation.vbet.to_mask`.
        transform: The raster's affine transform.

    Returns:
        A shapely geometry (the union of valley-bottom pixels), in the raster's CRS.
    """
    from rasterio.features import shapes

    geoms = [
        shape(geom)
        for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=transform)
        if value == 1
    ]
    if not geoms:
        raise ValueError("VBET mask is empty — no valley bottom to clip negatives to")
    return unary_union(geoms)
