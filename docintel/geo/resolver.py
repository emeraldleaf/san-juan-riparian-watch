"""Deterministic geo-resolver: free-form place mentions -> geometry (EPSG:4269).

The safe way to do "full free-form place resolution": resolve against **our own**
PostGIS layers first (HUC12, NHD flowlines, reaches), fall back to a gazetteer only
for places we don't hold — and always clip to the study-area AOI so a name that also
exists elsewhere in the country can't drag the map off-basin. Ambiguous mentions
return multiple candidates for the UI to disambiguate rather than guessing.

Resolution order (most-trusted first), per the spec:
    1. Internal layers — HUC id match, reach id, NHD flowline by GNIS name.
    2. Gazetteer fallback — GNIS/NHD names, AOI-clipped, lower confidence.
    3. Ambiguity — return all candidates; caller asks the user to pick.

See docs/specs/2026-07-04-document-intelligence-rag.md and the ADR. All metric math
uses PostGIS geography; storage/return CRS is EPSG:4269. Functions stay < 25 lines.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from .models import (
    GeoCandidate,
    GeoMention,
    MentionType,
    ResolvedGeometry,
    ResolvedKind,
)

logger = logging.getLogger(__name__)

# 12- and 8-digit HUC codes appear verbatim in agency documents.
_HUC12_RE = re.compile(r"\b(\d{12})\b")
_HUC8_RE = re.compile(r"\b(\d{8})\b")


class SpatialBackend(Protocol):
    """Read-only spatial lookups against the riparian PostGIS (injected, mockable).

    Each method returns ``GeoCandidate`` rows (already GeoJSON, EPSG:4269) or an
    empty list. Implementations bbox-pre-filter (``&&``) and AOI-clip; they never
    write. This Protocol is the seam that lets the resolver be unit-tested without
    a database (matches the project's Protocol-DI convention).
    """

    def huc_by_code(self, code: str) -> list[GeoCandidate]: ...
    def flowline_by_name(self, name: str) -> list[GeoCandidate]: ...
    def reach_by_name(self, name: str) -> list[GeoCandidate]: ...
    def gazetteer(self, name: str, mention_type: MentionType) -> list[GeoCandidate]: ...


class GeoResolver:
    """Resolves ``GeoMention``s to ``ResolvedGeometry`` deterministically.

    Args:
        backend: Spatial lookup implementation (PostGIS in prod, fake in tests).
        min_confidence: Candidates below this are dropped before selection.
    """

    def __init__(self, backend: SpatialBackend, *, min_confidence: float = 0.2) -> None:
        if backend is None:  # constructor null-guard (project convention)
            raise ValueError("backend is required")
        self._backend = backend
        self._min_confidence = min_confidence

    def resolve_all(self, mentions: list[GeoMention]) -> list[ResolvedGeometry]:
        """Resolve a batch, preserving input order."""
        return [self.resolve(m) for m in mentions]

    def resolve(self, mention: GeoMention) -> ResolvedGeometry:
        """Resolve one mention via the trusted-source-first ladder."""
        candidates = self._collect_candidates(mention)
        candidates = [c for c in candidates if c.confidence >= self._min_confidence]
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        deduped = self._dedupe(candidates)
        chosen = deduped[0] if deduped else None
        if chosen is None:
            logger.info("unresolved geo mention: %r", mention.mention_text)
        return ResolvedGeometry(
            mention_text=mention.mention_text,
            chosen=chosen,
            candidates=tuple(deduped),
        )

    # -- resolution ladder -------------------------------------------------

    def _collect_candidates(self, mention: GeoMention) -> list[GeoCandidate]:
        """Try each source in trust order; internal layers before the gazetteer."""
        out: list[GeoCandidate] = []
        out.extend(self._match_huc(mention))
        if mention.mention_type in (MentionType.REACH, MentionType.RIVER):
            out.extend(self._backend.reach_by_name(mention.mention_text))
        if mention.mention_type in (MentionType.RIVER, MentionType.PLACE, MentionType.REACH):
            out.extend(self._backend.flowline_by_name(mention.mention_text))
        # Gazetteer fallback only when internal layers found nothing trustworthy.
        if not out:
            out.extend(self._backend.gazetteer(mention.mention_text, mention.mention_type))
        return out

    def _match_huc(self, mention: GeoMention) -> list[GeoCandidate]:
        """Pull an explicit HUC code out of the text and look it up."""
        text = mention.mention_text
        m12 = _HUC12_RE.search(text)
        if m12:
            return self._backend.huc_by_code(m12.group(1))
        m8 = _HUC8_RE.search(text)
        if m8 and mention.mention_type == MentionType.HUC:
            return self._backend.huc_by_code(m8.group(1))
        return []

    @staticmethod
    def _dedupe(candidates: list[GeoCandidate]) -> list[GeoCandidate]:
        """Drop duplicate refs, keeping the highest-confidence occurrence."""
        seen: set[str] = set()
        result: list[GeoCandidate] = []
        for c in candidates:  # candidates are pre-sorted by confidence desc
            if c.ref not in seen:
                seen.add(c.ref)
                result.append(c)
        return result


# ---------------------------------------------------------------------------
# PostGIS backend — concrete SpatialBackend against the riparian database.
# Parameterized SQLAlchemy text() only (never string-concatenate input); bbox
# pre-filter + AOI clip; returns GeoJSON in EPSG:4269. Queries are the integration
# point — table/column names track sql/*_migration.sql. See CLAUDE.md "Data Access".
# ---------------------------------------------------------------------------


class PostGisSpatialBackend:
    """PostGIS implementation of ``SpatialBackend`` (SQLAlchemy engine injected).

    Args:
        engine: A SQLAlchemy Engine bound to the riparian database.
        aoi_huc: The study-area HUC prefix used to AOI-clip gazetteer hits
            (default subbasin 1408 — the San Juan River watershed).
    """

    def __init__(self, engine: object, *, aoi_huc: str = "1408") -> None:
        if engine is None:
            raise ValueError("engine is required")
        self._engine = engine
        self._aoi_huc = aoi_huc

    def huc_by_code(self, code: str) -> list[GeoCandidate]:
        # TODO(phase-c): SELECT ST_AsGeoJSON(geom), 'huc'||len AS kind FROM the HUC
        # polygon layer WHERE huc12 = :code OR huc8 = :code. HUC12 lives on
        # silver.riparian_extent / a HUC polygon table; confirm the source before wiring.
        raise NotImplementedError("wire to the HUC polygon layer (Phase C)")

    def flowline_by_name(self, name: str) -> list[GeoCandidate]:
        # TODO(phase-c): SELECT ST_AsGeoJSON(geom) FROM bronze.nhd_flowlines
        # WHERE gnis_name ILIKE :name AND huc12 LIKE :aoi || '%'  (AOI clip).
        raise NotImplementedError("wire to bronze.nhd_flowlines (Phase C)")

    def reach_by_name(self, name: str) -> list[GeoCandidate]:
        # TODO(phase-c): SELECT ST_AsGeoJSON(geom) FROM gold.reach_riparian
        # WHERE gnis_name ILIKE :name  (reaches already AOI-scoped by tile).
        raise NotImplementedError("wire to gold.reach_riparian (Phase C)")

    def gazetteer(self, name: str, mention_type: MentionType) -> list[GeoCandidate]:
        # TODO(phase-c): GNIS/NHD name lookup, then clip to the AOI bbox so a
        # same-named feature elsewhere in the US cannot pull the map off-basin.
        raise NotImplementedError("wire the AOI-clipped gazetteer fallback (Phase C)")
