"""Geo-mention + resolution data structures (document-intelligence geospatial half).

The LLM proposes *free-form* geographic mentions (``GeoMention``); the deterministic
resolver turns them into geometry (``ResolvedGeometry``). Keeping these as separate,
immutable types enforces the load-bearing invariant from the ADR: **the LLM never
emits geometry** — it only names places; shapes come from our PostGIS layers.

See docs/specs/2026-07-04-document-intelligence-rag.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MentionType(str, Enum):
    """Coarse type guess the extractor attaches to a free-form mention."""

    RIVER = "river"
    RESERVOIR = "reservoir"
    HUC = "huc"
    TOWN = "town"
    REACH = "reach"
    PLACE = "place"
    COORD = "coord"
    BBOX = "bbox"


class ResolvedKind(str, Enum):
    """What internal spatial key a mention resolved to (None-equivalent = unresolved)."""

    HUC12 = "huc12"
    HUC8 = "huc8"
    NHD_FLOWLINE = "nhd_flowline"
    REACH = "reach"
    GNIS = "gnis"


@dataclass(frozen=True)
class GeoMention:
    """A free-form geographic mention extracted from an answer or a chunk.

    Attributes:
        mention_text: The place as written, e.g. "Animas River near Farmington".
        mention_type: The extractor's coarse type guess.
        confidence: Extractor confidence in [0, 1].
        chunk_id: Optional Qdrant point id when the mention came from a stored
            chunk (ingest-time geo-tagging); None for answer-time mentions.
        page_start: Optional page anchor carried from the chunk for citations.
        page_end: Optional page anchor.
    """

    mention_text: str
    mention_type: MentionType
    confidence: float = 1.0
    chunk_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class GeoCandidate:
    """One resolution candidate for an ambiguous mention."""

    kind: ResolvedKind
    ref: str                      # e.g. "huc12=140801051001", "gnis=Animas River"
    geom_geojson: str             # GeoJSON geometry string (EPSG:4269)
    confidence: float


@dataclass(frozen=True)
class ResolvedGeometry:
    """A mention resolved to geometry, or a set of candidates when ambiguous.

    ``chosen`` is the best candidate (highest confidence, most-trusted source);
    ``candidates`` holds the full set so the UI can offer a disambiguation pick
    when ``len(candidates) > 1``. When nothing resolved, ``chosen is None`` and
    ``candidates`` is empty — the caller renders an "unresolved" affordance.
    """

    mention_text: str
    chosen: GeoCandidate | None
    candidates: tuple[GeoCandidate, ...] = field(default_factory=tuple)

    @property
    def is_resolved(self) -> bool:
        return self.chosen is not None

    @property
    def is_ambiguous(self) -> bool:
        return len(self.candidates) > 1
