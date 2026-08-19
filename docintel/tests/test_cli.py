"""Unit tests for riparian-cli — the typed tool layer, with the agent absent.

The point of the CLI is that each command has exactly one behaviour for fixed
inputs. ``resolve`` is exercised against a fake ``SpatialBackend`` (no DB); the
``map`` encoder is pure. Together they pin the load-bearing contract: the tool
*resolves* a place deterministically or reports it unresolved — it never guesses.
"""

from __future__ import annotations

import pytest

from docintel.cli import CliError, build_map_action, resolve_place
from docintel.geo.models import GeoCandidate, MentionType, ResolvedKind
from docintel.geo.resolver import GeoResolver

_GEOJSON = '{"type":"Point","coordinates":[-108.2,36.73]}'


def _cand(ref: str, confidence: float, kind: ResolvedKind = ResolvedKind.NHD_FLOWLINE) -> GeoCandidate:
    return GeoCandidate(kind, ref, _GEOJSON, confidence)


class FakeBackend:
    """A ``SpatialBackend`` that returns canned rows — the fixture, not the DB."""

    def __init__(self, *, flowlines=(), reaches=(), hucs=(), gazetteer=()) -> None:
        self._flowlines = list(flowlines)
        self._reaches = list(reaches)
        self._hucs = list(hucs)
        self._gazetteer = list(gazetteer)

    def huc_by_code(self, code: str) -> list[GeoCandidate]:
        return list(self._hucs)

    def flowline_by_name(self, name: str) -> list[GeoCandidate]:
        return list(self._flowlines)

    def reach_by_name(self, name: str) -> list[GeoCandidate]:
        return list(self._reaches)

    def gazetteer(self, name: str, mention_type: MentionType) -> list[GeoCandidate]:
        return list(self._gazetteer)


def _resolver(**backend_kwargs) -> GeoResolver:
    return GeoResolver(FakeBackend(**backend_kwargs))


# --- resolve --------------------------------------------------------------


def test_resolve_names_a_river_to_its_flowline() -> None:
    resolver = _resolver(flowlines=[_cand("gnis=Animas River", 0.92)])

    out = resolve_place(resolver, "Animas River", MentionType.PLACE)

    assert out["resolved"] is True
    assert out["ambiguous"] is False
    assert out["chosen"]["ref"] == "gnis=Animas River"
    assert out["chosen"]["kind"] == "nhd_flowline"
    assert out["chosen"]["geometry"]["type"] == "Point"  # geometry travels with the choice


def test_resolve_picks_highest_confidence_and_flags_ambiguity() -> None:
    resolver = _resolver(
        flowlines=[_cand("gnis=La Plata River", 0.68), _cand("gnis=Animas River", 0.92)]
    )

    out = resolve_place(resolver, "the river", MentionType.PLACE)

    assert out["ambiguous"] is True
    assert len(out["candidates"]) == 2
    assert out["chosen"]["ref"] == "gnis=Animas River"  # 0.92 beats 0.68
    assert "geometry" not in out["candidates"][0]  # alternatives stay lightweight


def test_resolve_leaves_an_unknown_town_unresolved_never_guesses() -> None:
    # A town with no gazetteer layer loaded is the honest unresolved case —
    # exactly PostGisSpatialBackend.gazetteer's real behaviour today.
    resolver = _resolver()

    out = resolve_place(resolver, "Farmington", MentionType.TOWN)

    assert out["resolved"] is False
    assert out["chosen"] is None
    assert out["candidates"] == []


def test_resolve_drops_candidates_below_min_confidence() -> None:
    resolver = _resolver(flowlines=[_cand("gnis=Faint Creek", 0.1)])

    out = resolve_place(resolver, "Faint Creek", MentionType.PLACE)

    assert out["resolved"] is False  # 0.1 < the resolver's 0.2 floor


# --- map ------------------------------------------------------------------


def test_map_fly_to_with_bbox() -> None:
    action = build_map_action("fly-to", bbox=[-108.3, 36.7, -108.1, 36.8], label="Farmington")

    assert action == {
        "event": "story:map",
        "action": "fly-to",
        "bbox": [-108.3, 36.7, -108.1, 36.8],
        "label": "Farmington",
    }


def test_map_highlight_with_geometry() -> None:
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}

    action = build_map_action("highlight", geometry=geom)

    assert action["action"] == "highlight"
    assert action["geometry"] == geom


def test_map_layer_toggle() -> None:
    assert build_map_action("layer", layer="wetlands", visible=False) == {
        "event": "story:map",
        "action": "layer",
        "layer": "wetlands",
        "visible": False,
    }


@pytest.mark.parametrize(
    "call",
    [
        lambda: build_map_action("zoom-out", bbox=[0, 0, 1, 1]),  # unknown action
        lambda: build_map_action("fly-to"),  # no target
        lambda: build_map_action("layer"),  # no --layer
    ],
)
def test_map_rejects_malformed_calls(call) -> None:
    with pytest.raises(CliError):
        call()
