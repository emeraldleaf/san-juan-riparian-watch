"""Per-reach riparian outputs (network-first Stage-1 product).

Fetches NHD flowlines for a HUC12 tile, splits them into ~250 m reaches, and
scores each reach with ``%riparian_cover`` from ``silver.riparian_extent`` within
a corridor buffer. Produces the manager-facing product: "which reaches are
riparian" (later "which are degrading"), interpretable along the river network.

All metric math (length, buffer, area) is done in EPSG:5070 (CONUS Albers,
metres); geometries are stored in EPSG:4269. NHD flowlines come from The
National Map (ArcGIS Large-Scale layer). See
docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import json
import logging

import requests
from shapely.geometry import shape as shapely_shape
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

NHD_FLOWLINE_QUERY = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
)
REACH_LEN_M = 250.0
CORRIDOR_M = 50.0
METRIC_SRID = 5070  # CONUS Albers Equal Area (metres)


# ---------------------------------------------------------------------------
# Fetch NHD flowlines (ArcGIS REST, paginated)
# ---------------------------------------------------------------------------


def fetch_flowlines(
    bbox: tuple[float, float, float, float], page: int = 500, timeout: int = 60,
) -> list[dict]:
    """Fetch NHD flowlines intersecting a bbox as GeoJSON-ish records.

    Args:
        bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4326/4269.
        page: Records per request.
        timeout: Per-request timeout (seconds).

    Returns:
        List of dicts with ``geom`` (shapely), ``permanent_id``, ``gnis_name``,
        ``fcode``.
    """
    env = {
        "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
        "spatialReference": {"wkid": 4326},
    }
    out: list[dict] = []
    offset = 0
    while True:
        params = {
            "geometry": json.dumps(env), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4269, "spatialRel": "esriSpatialRelIntersects",
            "where": "1=1", "outFields": "permanent_identifier,gnis_name,fcode",
            "returnGeometry": "true", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page,
        }
        feats = requests.get(NHD_FLOWLINE_QUERY, params=params, timeout=timeout).json().get(
            "features", [])
        if not feats:
            break
        for f in feats:
            g = f.get("geometry")
            if not g:
                continue
            props = f.get("properties", {})
            out.append({
                "geom": shapely_shape(g),
                "permanent_id": props.get("permanent_identifier"),
                "gnis_name": props.get("gnis_name"),
                "fcode": props.get("fcode"),
            })
        if len(feats) < page:
            break
        offset += page
    logger.info("NHD: fetched %d flowlines for %s", len(out), bbox)
    return out


# ---------------------------------------------------------------------------
# Persist flowlines
# ---------------------------------------------------------------------------


_DELETE_FLOWLINES = text("DELETE FROM bronze.nhd_flowlines WHERE huc12 = :huc12")
_INSERT_FLOWLINE = text("""
    INSERT INTO bronze.nhd_flowlines (permanent_id, gnis_name, fcode, huc12, geom)
    VALUES (:permanent_id, :gnis_name, :fcode, :huc12,
            ST_SetSRID(ST_GeomFromText(:wkt), 4269))
""")


def write_flowlines(engine: Engine, flowlines: list[dict], huc12: str) -> int:
    """Replace this tile's flowlines in bronze.nhd_flowlines (idempotent)."""
    if not flowlines:
        return 0
    params = [
        {
            "permanent_id": f["permanent_id"], "gnis_name": f["gnis_name"],
            "fcode": f["fcode"], "huc12": huc12, "wkt": f["geom"].wkt,
        }
        for f in flowlines
    ]
    with engine.connect() as conn:
        conn.execute(_DELETE_FLOWLINES, {"huc12": huc12})
        conn.execute(_INSERT_FLOWLINE, params)
        conn.commit()
    return len(flowlines)


# ---------------------------------------------------------------------------
# Split into reaches + score riparian cover (PostGIS, all metric math in 5070)
# ---------------------------------------------------------------------------


_BUILD_REACHES = text("""
    DELETE FROM gold.reach_riparian WHERE huc12 = :huc12 AND method = :method;

    WITH parts AS (
        SELECT permanent_id, gnis_name, huc12,
               (ST_Dump(ST_LineMerge(geom))).geom AS geom
        FROM bronze.nhd_flowlines
        WHERE huc12 = :huc12
    ),
    measured AS (
        SELECT permanent_id, gnis_name, huc12, geom,
               ST_Length(geom::geography) AS len_m
        FROM parts
        WHERE ST_GeometryType(geom) = 'ST_LineString'
          AND ST_Length(geom::geography) > 0
    ),
    reaches AS (
        SELECT permanent_id, gnis_name, huc12, gs AS reach_index,
               ST_LineSubstring(
                   geom,
                   LEAST(gs * :reach_len / len_m, 1.0),
                   LEAST((gs + 1) * :reach_len / len_m, 1.0)
               ) AS geom
        FROM measured,
             LATERAL generate_series(
                 0, GREATEST(0, CEIL(len_m / :reach_len)::int - 1)
             ) AS gs
    ),
    scored AS (
        -- Corridor as a 4269-labelled polygon so the GiST index on
        -- riparian_extent.geom is usable in the join. The geography buffer is
        -- metric; the 4326→4269 relabel is a sub-metre fudge, negligible here.
        SELECT permanent_id, gnis_name, huc12, reach_index, geom,
               ST_Length(geom::geography) AS reach_len_m,
               ST_SetSRID(ST_Buffer(geom::geography, :corridor)::geometry, 4269) AS corridor
        FROM reaches
        WHERE ST_Length(geom::geography) > 1
    ),
    cover AS (
        SELECT s.permanent_id, s.gnis_name, s.huc12, s.reach_index, s.geom,
               s.reach_len_m, ST_Area(s.corridor::geography) AS corr_area,
               COALESCE(SUM(ST_Area(
                   ST_Intersection(s.corridor, e.geom)::geography)), 0) AS rip_area
        FROM scored s
        LEFT JOIN silver.riparian_extent e
          ON e.huc12 = s.huc12 AND e.method = :method
          AND ST_Intersects(s.corridor, e.geom)
        GROUP BY s.permanent_id, s.gnis_name, s.huc12, s.reach_index, s.geom,
                 s.reach_len_m, s.corridor
    )
    INSERT INTO gold.reach_riparian
        (permanent_id, gnis_name, huc12, reach_index, method, length_m,
         corridor_m, riparian_cover_pct, geom)
    SELECT permanent_id, gnis_name, huc12, reach_index, :method,
           ROUND(reach_len_m::numeric, 2), :corridor,
           LEAST(100.0, ROUND((100.0 * rip_area / NULLIF(corr_area, 0))::numeric, 2)),
           geom
    FROM cover;
""")


def build_reaches(
    engine: Engine,
    huc12: str,
    *,
    method: str = "rf",
    reach_len_m: float = REACH_LEN_M,
    corridor_m: float = CORRIDOR_M,
) -> int:
    """Split this tile's flowlines into reaches and score %riparian_cover.

    Returns:
        The number of reaches written.
    """
    with engine.connect() as conn:
        conn.execute(_BUILD_REACHES, {
            "huc12": huc12, "method": method, "srid": METRIC_SRID,
            "reach_len": reach_len_m, "corridor": corridor_m,
        })
        conn.commit()
        n = conn.execute(
            text("SELECT count(*) FROM gold.reach_riparian "
                 "WHERE huc12 = :huc12 AND method = :method"),
            {"huc12": huc12, "method": method},
        ).scalar_one()
    logger.info("Wrote %d reaches for %s (method %s)", n, huc12, method)
    return int(n)


def process_tile_reaches(
    engine: Engine,
    huc12: str,
    bbox: tuple[float, float, float, float],
    *,
    method: str = "rf",
) -> int:
    """End-to-end: fetch NHD flowlines for a tile, persist, split + score reaches."""
    flowlines = fetch_flowlines(bbox)
    written = write_flowlines(engine, flowlines, huc12)
    logger.info("Persisted %d flowlines for %s", written, huc12)
    return build_reaches(engine, huc12, method=method)
