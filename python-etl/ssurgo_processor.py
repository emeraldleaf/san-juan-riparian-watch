"""SSURGO soil data processor.

Fetches soil map unit polygons from the NRCS Soil Data Access WFS service
and hydric rating data from the tabular POST REST service.  Writes to
bronze.ssurgo_soils and computes buffer-soil intersections in silver.buffer_soils.

Data sources:
  - Spatial: https://SDMDataAccess.sc.egov.usda.gov/Spatial/SDMNAD83Geographic.wfs
  - Tabular: https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import geopandas as gpd
import pandas as pd
import requests
from lxml import etree
from shapely.geometry import box
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NRCS Soil Data Access — NAD83 WFS (EPSG:4269, matches our storage CRS)
WFS_URL = "https://SDMDataAccess.sc.egov.usda.gov/Spatial/SDMNAD83Geographic.wfs"

# NRCS Soil Data Access — tabular POST REST
TABULAR_URL = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"

# Feature type name for map unit polygons
MAPUNIT_TYPENAME = "MapunitPoly"

# Maximum features per WFS request
WFS_MAX_FEATURES = 50_000

# Maximum bbox span (degrees) per WFS request — NRCS rejects large bboxes
WFS_MAX_SPAN_DEG = 0.5

# HTTP timeout in seconds
HTTP_TIMEOUT = 120

# GML namespace map for parsing WFS GetFeature responses
GML_NS = {
    "gml": "http://www.opengis.net/gml",
    "ms": "http://mapserver.gis.umn.edu/mapserver",
    "wfs": "http://www.opengis.net/wfs",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoilMapUnit:
    """A single SSURGO soil map unit with optional hydric data."""

    mukey: str
    musym: str | None
    muname: str | None
    hydric_rating: str | None
    hydric_pct: float | None


@dataclass(frozen=True)
class BufferSoil:
    """Result of buffer-soil intersection."""

    buffer_id: int
    soil_id: int
    overlap_area_sq_m: float
    soil_pct_of_buffer: float
    hydric_rating: str | None
    hydric_pct: float | None
    muname: str | None


# ---------------------------------------------------------------------------
# Writer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SoilWriter(Protocol):
    """Protocol for writing SSURGO soil data."""

    def truncate(self, schema: str, table: str, cascade: bool = False) -> None: ...
    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> int: ...
    def write(self, gdf: gpd.GeoDataFrame, table: str, schema: str) -> None: ...


# ---------------------------------------------------------------------------
# WFS Client
# ---------------------------------------------------------------------------


def fetch_mapunit_polygons(
    bbox: tuple[float, float, float, float],
    *,
    srs: str = "EPSG:4269",
) -> gpd.GeoDataFrame:
    """Fetch SSURGO MapunitPoly features via WFS GetFeature with BBOX.

    The SDM WFS uses GML2 format and requires the bbox as a GML Filter.
    Large bounding boxes are automatically chunked to stay within the
    NRCS server limits.

    Args:
        bbox: (xmin, ymin, xmax, ymax) in the target SRS.
        srs: Spatial reference system code.

    Returns:
        GeoDataFrame with mukey, musym, muname columns + geometry.
    """
    xmin, ymin, xmax, ymax = bbox
    x_span = xmax - xmin
    y_span = ymax - ymin

    # Chunk large bboxes to avoid the 400 Bad Request from NRCS
    if x_span > WFS_MAX_SPAN_DEG or y_span > WFS_MAX_SPAN_DEG:
        import math

        n_x = math.ceil(x_span / WFS_MAX_SPAN_DEG)
        n_y = math.ceil(y_span / WFS_MAX_SPAN_DEG)
        dx = x_span / n_x
        dy = y_span / n_y
        logger.info(
            "Chunking SSURGO bbox into %dx%d tiles (%.4f° x %.4f°)",
            n_x, n_y, dx, dy,
        )
        parts: list[gpd.GeoDataFrame] = []
        for ix in range(n_x):
            for iy in range(n_y):
                sub_bbox = (
                    xmin + ix * dx,
                    ymin + iy * dy,
                    xmin + (ix + 1) * dx,
                    ymin + (iy + 1) * dy,
                )
                try:
                    chunk = _fetch_wfs_chunk(sub_bbox, srs=srs)
                    if not chunk.empty:
                        parts.append(chunk)
                except Exception:
                    logger.warning(
                        "SSURGO WFS chunk %.4f,%.4f,%.4f,%.4f failed — skipping",
                        *sub_bbox, exc_info=True,
                    )
        if not parts:
            return gpd.GeoDataFrame()
        gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
        # Deduplicate — chunks overlap at edges
        if "mukey" in gdf.columns:
            gdf = gdf.drop_duplicates(subset=["mukey", "geometry"])
        logger.info("Fetched %d total SSURGO map unit polygons from %d chunks", len(gdf), len(parts))
        return gdf

    return _fetch_wfs_chunk(bbox, srs=srs)


def _fetch_wfs_chunk(
    bbox: tuple[float, float, float, float],
    *,
    srs: str = "EPSG:4269",
) -> gpd.GeoDataFrame:
    """Fetch a single SSURGO WFS chunk for a small bbox."""
    xmin, ymin, xmax, ymax = bbox
    logger.info(
        "Fetching SSURGO MapunitPoly via WFS — bbox: %.4f,%.4f,%.4f,%.4f",
        xmin, ymin, xmax, ymax,
    )

    # WFS GetFeature with BBOX filter (GML format for SDM WFS 1.1.0)
    gml_filter = (
        f"<Filter>"
        f"<BBOX>"
        f"<PropertyName>Geometry</PropertyName>"
        f"<Box srsName='{srs}'>"
        f"<coordinates>{xmin},{ymin} {xmax},{ymax}</coordinates>"
        f"</Box>"
        f"</BBOX>"
        f"</Filter>"
    )

    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": MAPUNIT_TYPENAME,
        "SRSNAME": srs,
        "FILTER": gml_filter,
        "OUTPUTFORMAT": "GML2",
        "MAXFEATURES": str(WFS_MAX_FEATURES),
    }

    response = requests.get(WFS_URL, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()

    # Parse GML response into GeoDataFrame
    # gpd.read_file can read GML from bytes
    gdf = gpd.read_file(io.BytesIO(response.content), driver="GML")

    if gdf.empty:
        logger.warning("No SSURGO features returned from WFS for bbox")
        return gdf

    logger.info("Fetched %d SSURGO map unit polygons from WFS", len(gdf))

    # Standardize column names — SDM WFS returns varying case
    col_map = {}
    for col in gdf.columns:
        lower = col.lower()
        if lower == "mukey":
            col_map[col] = "mukey"
        elif lower == "musym":
            col_map[col] = "musym"
        elif lower == "muname":
            col_map[col] = "muname"
    gdf = gdf.rename(columns=col_map)

    # Ensure we have the mukey column
    if "mukey" not in gdf.columns:
        # Try to extract from other fields — musym sometimes used
        raise ValueError("WFS response missing 'mukey' column")

    # Keep only needed columns
    keep = [c for c in ["mukey", "musym", "muname"] if c in gdf.columns]
    keep.append("geometry")
    gdf = gdf[keep].copy()

    # Ensure geometry is MultiPolygon and CRS is 4269
    gdf = gdf.set_geometry("geometry")
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4269)
    elif gdf.crs.to_epsg() != 4269:
        gdf = gdf.to_crs(epsg=4269)

    # Convert all geometries to MultiPolygon for consistency
    gdf["geometry"] = gdf["geometry"].apply(_ensure_multi)

    # Rename geometry column for PostGIS
    gdf = gdf.rename_geometry("geom")

    return gdf


def _ensure_multi(geom: Any) -> Any:
    """Convert Polygon to MultiPolygon for consistent storage."""
    from shapely.geometry import MultiPolygon, Polygon

    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    return geom


# ---------------------------------------------------------------------------
# Tabular hydric data
# ---------------------------------------------------------------------------


def _parse_hydric_response(
    data: dict,
) -> dict[str, tuple[str | None, float | None]]:
    """Parse a JSON+COLUMNNAME hydric rating response into a dict.

    Args:
        data: Raw JSON from the NRCS tabular endpoint.

    Returns:
        Dict mapping mukey → (hydric_rating, hydric_pct).
    """
    parsed: dict[str, tuple[str | None, float | None]] = {}
    if "Table" not in data or len(data["Table"]) <= 1:
        return parsed

    headers = data["Table"][0]
    for row in data["Table"][1:]:
        row_dict = dict(zip(headers, row))
        mk = str(row_dict.get("mukey", ""))
        if not mk:
            continue
        rating = row_dict.get("hydric_rating") or None
        pct = row_dict.get("hydric_pct")
        parsed[mk] = (
            rating,
            float(pct) if pct is not None else None,
        )
    return parsed


def _fetch_hydric_batch(
    batch: list[str],
    batch_index: int,
) -> dict[str, tuple[str | None, float | None]]:
    """Fetch hydric ratings for a single batch of mukeys.

    Args:
        batch: List of mukey strings for this batch.
        batch_index: Starting offset (for logging).

    Returns:
        Dict mapping mukey → (hydric_rating, hydric_pct).
    """
    mukey_list = ",".join(f"'{mk}'" for mk in batch)
    query = f"""
        SELECT
            m.mukey,
            m.hydricrating AS hydric_rating,
            CAST(
                ISNULL(
                    (SELECT SUM(c.comppct_r)
                     FROM component c
                     WHERE c.mukey = m.mukey
                     AND c.hydricrating = 'Yes'), 0
                ) AS DECIMAL(5,2)
            ) AS hydric_pct
        FROM mapunit m
        WHERE m.mukey IN ({mukey_list})
    """
    payload = {"QUERY": query, "FORMAT": "JSON+COLUMNNAME"}

    try:
        response = requests.post(TABULAR_URL, data=payload, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return _parse_hydric_response(response.json())
    except Exception:
        logger.exception(
            "Failed to fetch hydric ratings for batch %d–%d",
            batch_index, batch_index + len(batch),
        )
        return {}


def fetch_hydric_ratings(mukeys: list[str]) -> dict[str, tuple[str | None, float | None]]:
    """Fetch hydric soil ratings from NRCS Soil Data Access tabular service.

    Uses the POST REST endpoint with a SQL query against the component table
    to get hydric ratings and percentages per map unit.

    Args:
        mukeys: List of map unit key values.

    Returns:
        Dict mapping mukey → (hydric_rating, hydric_pct).
    """
    if not mukeys:
        return {}

    logger.info("Fetching hydric ratings for %d map units", len(mukeys))

    batch_size = 500
    results: dict[str, tuple[str | None, float | None]] = {}

    for i in range(0, len(mukeys), batch_size):
        batch = mukeys[i : i + batch_size]
        results.update(_fetch_hydric_batch(batch, i))

    logger.info("Retrieved hydric ratings for %d map units", len(results))
    return results


# ---------------------------------------------------------------------------
# SSURGO Processor (orchestrator)
# ---------------------------------------------------------------------------


class SsurgoProcessor:
    """Orchestrates SSURGO soil data loading and buffer intersection.

    Sequence:
      1. Fetch soil polygons from WFS
      2. Fetch hydric ratings from tabular service
      3. Join and write to bronze.ssurgo_soils
      4. Compute buffer-soil intersection → silver.buffer_soils
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def load_soils(self, bbox: tuple[float, float, float, float]) -> int:
        """Fetch SSURGO data and write to bronze.ssurgo_soils.

        Args:
            bbox: (xmin, ymin, xmax, ymax) in EPSG:4269.

        Returns:
            Number of soil map units loaded.
        """
        # 1. Fetch spatial polygons from WFS
        gdf = fetch_mapunit_polygons(bbox)
        if gdf.empty:
            logger.warning("No SSURGO polygons fetched — skipping")
            return 0

        # 2. Fetch hydric ratings from tabular service
        mukeys = gdf["mukey"].dropna().unique().tolist()
        hydric = fetch_hydric_ratings(mukeys)

        # 3. Merge hydric data
        gdf["hydric_rating"] = gdf["mukey"].map(
            lambda mk: hydric.get(str(mk), (None, None))[0]  # noqa: B023
        )
        gdf["hydric_pct"] = gdf["mukey"].map(
            lambda mk: hydric.get(str(mk), (None, None))[1]  # noqa: B023
        )

        # Fill missing columns
        for col in ["musym", "muname"]:
            if col not in gdf.columns:
                gdf[col] = None

        # 4. Deduplicate by mukey — WFS may return overlapping tiles
        #    Keep the first geometry per mukey
        gdf = gdf.drop_duplicates(subset="mukey", keep="first")

        # 5. Write to bronze — truncate and replace
        logger.info("Writing %d soil map units to bronze.ssurgo_soils", len(gdf))
        with self._engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE bronze.ssurgo_soils CASCADE"))
            conn.commit()

        gdf[["mukey", "musym", "muname", "hydric_rating", "hydric_pct", "geom"]].to_postgis(
            "ssurgo_soils",
            self._engine,
            schema="bronze",
            if_exists="append",
            index=False,
        )
        logger.info("Wrote %d soil map units to bronze.ssurgo_soils", len(gdf))
        return len(gdf)

    def analyze_buffer_soils(self) -> int:
        """Compute spatial intersection of buffers with soil polygons.

        Returns:
            Number of buffer-soil overlaps found.
        """
        logger.info("Analyzing buffer-soil intersections")
        with self._engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE silver.buffer_soils"))
            conn.commit()

        sql = text("""
            WITH intersections AS (
                SELECT
                    b.id AS buffer_id,
                    s.id AS soil_id,
                    b.area_sq_m AS buffer_area_sq_m,
                    s.hydric_rating,
                    s.hydric_pct,
                    s.muname,
                    ST_Intersection(b.geom, s.geom) AS overlap_geom
                FROM silver.riparian_buffers b
                JOIN bronze.ssurgo_soils s
                    ON b.geom && s.geom
                    AND ST_Intersects(b.geom, s.geom)
            )
            INSERT INTO silver.buffer_soils (
                buffer_id, soil_id, overlap_area_sq_m,
                soil_pct_of_buffer, hydric_rating, hydric_pct, muname
            )
            SELECT
                i.buffer_id,
                i.soil_id,
                ST_Area(i.overlap_geom::geography),
                ST_Area(i.overlap_geom::geography)
                    / NULLIF(i.buffer_area_sq_m, 0) * 100,
                i.hydric_rating,
                i.hydric_pct,
                i.muname
            FROM intersections i
            WHERE ST_Area(i.overlap_geom::geography) > 1
        """)

        with self._engine.connect() as conn:
            result = conn.execute(sql)
            conn.commit()
            count = result.rowcount

        logger.info("Found %d buffer-soil overlaps", count)
        return count

    def process(self, bbox: tuple[float, float, float, float]) -> None:
        """Run the full SSURGO processing pipeline.

        Args:
            bbox: Study area bounding box (xmin, ymin, xmax, ymax) in EPSG:4269.
        """
        loaded = self.load_soils(bbox)
        if loaded > 0:
            self.analyze_buffer_soils()
        logger.info("SSURGO processing complete")
