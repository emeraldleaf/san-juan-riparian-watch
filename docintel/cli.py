"""riparian-cli — the map agent's typed, deterministic tool layer.

The conversational map agent (docs/specs/2026-08-18-conversational-map-agent.md)
is nondeterministic; its tooling is not. Each subcommand takes typed flags and
prints exactly one JSON object to stdout, so every tool call has one behaviour
and is unit-testable with the agent absent.

Phase 1 commands:
  resolve <place>   free-form place -> typed geometry (resolve, don't guess)
  area --metric ... an aggregate metric for a geometry, with provenance
  map <action>      one deterministic frontend map action (a story:map event)

`find` — feature filters against the C# spatial API — is the next increment (see
the spec's Phasing section).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from docintel.geo.models import GeoCandidate, GeoMention, MentionType
from docintel.geo.resolver import GeoResolver

logger = logging.getLogger("riparian_cli")

_MAP_ACTIONS = ("fly-to", "highlight", "layer")
_AREA_METRICS = ("extent", "health-grade")
_METHODS = ("rf", "olmoearth")
_DEFAULT_API_URL = "http://localhost:8000"


class CliError(Exception):
    """A user-facing CLI failure (bad flags, or the backend is unreachable)."""


# --- resolve --------------------------------------------------------------


def build_resolver() -> GeoResolver:
    """Construct the production resolver (PostGIS) from ``RIPARIANDB_URI``.

    Imported lazily so ``map`` — which needs no database — stays dependency-free.

    Raises:
        CliError: when ``RIPARIANDB_URI`` is unset.
    """
    uri = os.environ.get("RIPARIANDB_URI")
    if not uri:
        raise CliError("RIPARIANDB_URI is not set; cannot reach the spatial backend")
    from sqlalchemy import create_engine

    from docintel.geo.resolver import PostGisSpatialBackend

    return GeoResolver(PostGisSpatialBackend(create_engine(uri)))


def _candidate_dict(candidate: GeoCandidate, *, geometry: bool) -> dict[str, Any]:
    """Serialize a candidate; the (large) geometry is opt-in."""
    out: dict[str, Any] = {
        "kind": candidate.kind.value,
        "ref": candidate.ref,
        "confidence": candidate.confidence,
    }
    if geometry:
        out["geometry"] = json.loads(candidate.geom_geojson)
    return out


def resolve_place(
    resolver: GeoResolver, place: str, mention_type: MentionType
) -> dict[str, Any]:
    """Resolve a free-form place to typed geometry — resolve, don't guess.

    The chosen candidate carries geometry (the agent feeds it to ``map``); the
    rest carry only ref + confidence, so the agent can ask the user to
    disambiguate when ``ambiguous`` is true rather than picking blind.
    """
    result = resolver.resolve(GeoMention(mention_text=place, mention_type=mention_type))
    return {
        "mention": result.mention_text,
        "resolved": result.is_resolved,
        "ambiguous": result.is_ambiguous,
        "chosen": _candidate_dict(result.chosen, geometry=True) if result.chosen else None,
        "candidates": [_candidate_dict(c, geometry=False) for c in result.candidates],
    }


# --- area -----------------------------------------------------------------


def query_area(
    metric: str,
    geometry: dict[str, Any],
    *,
    api_url: str,
    method: str = "rf",
) -> dict[str, Any]:
    """Query an aggregate metric for a geometry from the C# spatial API.

    The geometry is one the agent resolved via ``resolve``; the API returns the
    value with its provenance (the schema it came from) so the answer can cite it.

    Raises:
        CliError: on an unknown metric, or when the API is unreachable / errors.
    """
    if metric not in _AREA_METRICS:
        raise CliError(f"unknown --metric {metric!r}; choose {_AREA_METRICS}")
    endpoint = f"{api_url.rstrip('/')}/api/agent/area"
    payload = json.dumps(
        {"metric": metric, "method": method, "geometry": geometry}
    ).encode()
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise CliError(f"spatial API returned {exc.code} at {endpoint}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"spatial API unreachable at {endpoint}: {exc.reason}") from exc


# --- map ------------------------------------------------------------------


def _parse_bbox(raw: str) -> list[float]:
    """Parse ``minx,miny,maxx,maxy`` (EPSG:4269) into four floats."""
    try:
        parts = [float(x) for x in raw.split(",")]
    except ValueError as exc:
        raise CliError(f"invalid --bbox {raw!r}: expected four numbers") from exc
    if len(parts) != 4:
        raise CliError(f"invalid --bbox {raw!r}: expected minx,miny,maxx,maxy")
    return parts


def build_map_action(
    action: str,
    *,
    bbox: list[float] | None = None,
    geometry: dict[str, Any] | None = None,
    label: str | None = None,
    layer: str | None = None,
    visible: bool = True,
) -> dict[str, Any]:
    """Encode one deterministic frontend map action (a ``story:map`` event).

    ``fly-to`` / ``highlight`` target an area (``bbox`` or ``geometry``);
    ``layer`` toggles a named map layer on or off.
    """
    if action not in _MAP_ACTIONS:
        raise CliError(f"unknown map action {action!r}; choose {_MAP_ACTIONS}")
    payload: dict[str, Any] = {"event": "story:map", "action": action}
    if action == "layer":
        if not layer:
            raise CliError("map layer requires --layer")
        return {**payload, "layer": layer, "visible": visible}
    if bbox is None and geometry is None:
        raise CliError(f"map {action} requires --bbox or --geojson")
    if bbox is not None:
        payload["bbox"] = bbox
    if geometry is not None:
        payload["geometry"] = geometry
    if label:
        payload["label"] = label
    return payload


# --- argparse plumbing ----------------------------------------------------


def _read_text(source: str) -> str:
    """Read a file path, or all of stdin when ``source`` is ``-``."""
    if source == "-":
        return sys.stdin.read()
    try:
        with open(source, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError(f"cannot read {source!r}: {exc}") from exc


def _load_geojson(source: str) -> dict[str, Any]:
    """Load a GeoJSON geometry from a file path, or ``-`` for stdin."""
    try:
        return json.loads(_read_text(source))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid GeoJSON from {source!r}: {exc}") from exc


def _run_resolve(args: argparse.Namespace) -> dict[str, Any]:
    return resolve_place(build_resolver(), args.place, MentionType(args.type))


def _run_area(args: argparse.Namespace) -> dict[str, Any]:
    return query_area(
        args.metric,
        _load_geojson(args.geojson),
        api_url=args.api_url,
        method=args.method,
    )


def _run_map(args: argparse.Namespace) -> dict[str, Any]:
    return build_map_action(
        args.action,
        bbox=_parse_bbox(args.bbox) if args.bbox else None,
        geometry=_load_geojson(args.geojson) if args.geojson else None,
        label=args.label,
        layer=args.layer,
        visible=not args.hide,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riparian-cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve", help="free-form place -> typed geometry")
    p_resolve.add_argument("place")
    p_resolve.add_argument(
        "--type",
        default=MentionType.PLACE.value,
        choices=[t.value for t in MentionType],
        help="the extractor's coarse type guess for the mention",
    )
    p_resolve.set_defaults(func=_run_resolve)

    p_area = sub.add_parser("area", help="an aggregate metric for a geometry")
    p_area.add_argument("--metric", required=True, choices=_AREA_METRICS)
    p_area.add_argument(
        "--geojson", required=True, help="geometry file path, or - for stdin"
    )
    p_area.add_argument("--method", default="rf", choices=_METHODS)
    p_area.add_argument(
        "--api-url",
        default=os.environ.get("RIPARIAN_API_URL", _DEFAULT_API_URL),
        help="C# spatial API base URL",
    )
    p_area.set_defaults(func=_run_area)

    p_map = sub.add_parser("map", help="emit one story:map frontend action")
    p_map.add_argument("action", choices=_MAP_ACTIONS)
    p_map.add_argument("--bbox", help="minx,miny,maxx,maxy (EPSG:4269)")
    p_map.add_argument("--geojson", help="geometry file path, or - for stdin")
    p_map.add_argument("--label", help="human label shown on the map")
    p_map.add_argument("--layer", help="layer id (for the layer action)")
    p_map.add_argument("--hide", action="store_true", help="layer: hide instead of show")
    p_map.set_defaults(func=_run_map)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse args, run the subcommand, print its JSON result; return an exit code."""
    logging.basicConfig(level=logging.WARNING)
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except CliError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
