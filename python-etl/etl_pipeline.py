"""Riparian Buffer Compliance ETL Pipeline.

Orchestrates data ingestion from ArcGIS REST services into the
medallion architecture (bronze -> silver -> gold) in PostGIS.

Study area: San Juan Basin, HUC8 14080101.
"""

import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import geopandas as gpd
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ArcGIS REST endpoints
WATERSHED_URL = (
    "https://apps.fs.usda.gov/ArcX/rest/services"
    "/EDW/EDW_Watersheds_01/MapServer/3"
)
NHDPLUS_URL = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services"
    "/NHDPlusV21/FeatureServer"
)
NHDPLUS_FLOWLINE_LAYER = 2
NHDPLUS_WATERBODY_LAYER = 1
NHDPLUS_SINK_LAYER = 0
PARCELS_URL = (
    "https://gis.colorado.gov/public/rest/services"
    "/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0"
)

# Study area
HUC8_CODE = "14080101"

# Spatial
STORAGE_CRS = "EPSG:4269"
DEFAULT_BUFFER_DISTANCE_M = 30.48  # 100 feet

# ArcGIS pagination
ARCGIS_BATCH_SIZE = 1000

# NHDPlus feature type code for sinks
SINK_FTYPE = 378

# Parcel field renaming (source API field -> database column)
PARCEL_FIELD_MAP: dict[str, str] = {
    "parcel_id": "parcel_id",
    "landUseDsc": "land_use_desc",
    "landUseCde": "land_use_code",
    "zoningDesc": "zoning_desc",
    "owner": "owner_name",
    "landAcres": "land_acres",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerChangeResult:
    """Result of an incremental layer load."""

    layer_name: str
    inserted: int
    updated: int
    skipped: int

    @property
    def has_changes(self) -> bool:
        """True if any rows were inserted or updated."""
        return self.inserted > 0 or self.updated > 0


# ---------------------------------------------------------------------------
# Protocols (interfaces for dependency injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class FeatureClient(Protocol):
    """Interface for fetching geospatial features from a REST API."""

    def query(
        self,
        url: str,
        where: str = "1=1",
        out_fields: str = "*",
        geometry_filter: dict[str, Any] | None = None,
        result_offset: int | None = None,
        result_record_count: int | None = None,
    ) -> gpd.GeoDataFrame:
        """Fetch features as a GeoDataFrame."""
        ...


@runtime_checkable
class SpatialWriter(Protocol):
    """Interface for writing geospatial data to a database."""

    def count_rows(self, schema: str, table: str) -> int:
        """Return row count for a table."""
        ...

    def truncate(self, schema: str, table: str, cascade: bool = False) -> None:
        """Truncate a table, optionally cascading to dependents."""
        ...

    def write(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
        schema: str,
    ) -> None:
        """Append a GeoDataFrame to a PostGIS table."""
        ...

    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> int:
        """Execute a SQL statement and return affected row count."""
        ...

    def get_watershed_envelope(self, huc8: str) -> dict[str, Any]:
        """Get the bounding box of a watershed as an ArcGIS filter dict."""
        ...

    def upsert(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
        schema: str,
        conflict_column: str,
        update_columns: list[str],
    ) -> tuple[int, int]:
        """Upsert via ON CONFLICT. Returns (inserted, updated)."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class ArcGISFeatureClient:
    """Fetches geospatial features from ArcGIS REST API endpoints."""

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    def query(
        self,
        url: str,
        where: str = "1=1",
        out_fields: str = "*",
        geometry_filter: dict[str, Any] | None = None,
        result_offset: int | None = None,
        result_record_count: int | None = None,
    ) -> gpd.GeoDataFrame:
        """Fetch features from an ArcGIS REST endpoint as a GeoDataFrame.

        Args:
            url: Full URL to the layer (including layer ID).
            where: SQL WHERE clause for attribute filtering.
            out_fields: Comma-separated field names or "*".
            geometry_filter: Dict with geometry, geometryType, spatialRel.
            result_offset: Pagination offset.
            result_record_count: Page size.

        Returns:
            GeoDataFrame in EPSG:4269, or empty GeoDataFrame if no features.

        Raises:
            requests.HTTPError: If the API request fails.
        """
        params = self._build_params(
            where, out_fields, geometry_filter,
            result_offset, result_record_count,
        )
        response = requests.get(
            f"{url}/query", params=params, timeout=self._timeout,
        )
        response.raise_for_status()

        features = response.json().get("features", [])
        if not features:
            return gpd.GeoDataFrame()
        return gpd.GeoDataFrame.from_features(features, crs="EPSG:4269")

    def _build_params(
        self,
        where: str,
        out_fields: str,
        geometry_filter: dict[str, Any] | None,
        result_offset: int | None,
        result_record_count: int | None,
    ) -> dict[str, Any]:
        """Build the query parameter dict for an ArcGIS REST request."""
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "outSR": 4269,
            "f": "geojson",
        }
        if geometry_filter:
            params.update(geometry_filter)
        if result_offset is not None:
            params["resultOffset"] = result_offset
        if result_record_count is not None:
            params["resultRecordCount"] = result_record_count
        return params


class PostGISWriter:
    """Writes geospatial data to PostGIS via SQLAlchemy."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def count_rows(self, schema: str, table: str) -> int:
        """Return row count for a table."""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT count(*) FROM {schema}.{table}"),  # noqa: S608
            ).fetchone()
        return int(row[0]) if row else 0

    def truncate(self, schema: str, table: str, cascade: bool = False) -> None:
        """Truncate a table.

        Args:
            schema: Target schema name.
            table: Target table name.
            cascade: If True, cascade to dependent tables. Default False
                to prevent accidentally wiping expensive derived data
                (e.g. vegetation_health via riparian_buffers FK).
        """
        suffix = " CASCADE" if cascade else ""
        with self._engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {schema}.{table}{suffix}"))  # noqa: S608
            conn.commit()

    def write(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
        schema: str,
    ) -> None:
        """Append a GeoDataFrame to a PostGIS table."""
        gdf.to_postgis(
            table, self._engine, schema=schema,
            if_exists="append", index=False,
        )
        logger.info("Wrote %d rows to %s.%s", len(gdf), schema, table)

    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> int:
        """Execute a SQL statement and return affected row count."""
        with self._engine.connect() as conn:
            result = conn.execute(sql, params or {})
            conn.commit()
        return result.rowcount

    def get_watershed_envelope(self, huc8: str) -> dict[str, Any]:
        """Get the bounding box of a watershed as an ArcGIS filter dict.

        Args:
            huc8: The HUC8 watershed code.

        Returns:
            ArcGIS-compatible geometry filter dict.

        Raises:
            RuntimeError: If no watershed is found for the given HUC8.
        """
        query = text(
            "SELECT ST_XMin(geom) AS xmin, ST_YMin(geom) AS ymin, "
            "ST_XMax(geom) AS xmax, ST_YMax(geom) AS ymax "
            "FROM bronze.watersheds WHERE huc8 = :huc8 LIMIT 1"
        )
        with self._engine.connect() as conn:
            row = conn.execute(query, {"huc8": huc8}).fetchone()
        if row is None:
            raise RuntimeError(f"No watershed found for HUC8 {huc8}")

        return {
            "geometry": f"{row.xmin},{row.ymin},{row.xmax},{row.ymax}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4269",
        }

    def upsert(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
        schema: str,
        conflict_column: str,
        update_columns: list[str],
    ) -> tuple[int, int]:
        """Upsert a GeoDataFrame using a staging table + ON CONFLICT.

        Args:
            gdf: Data to upsert.
            table: Target table name.
            schema: Target schema name.
            conflict_column: Column with UNIQUE constraint for conflict detection.
            update_columns: Columns to update on conflict.

        Returns:
            Tuple of (rows inserted, rows updated).
        """
        staging = f"_staging_{table}"

        # Write to staging table (replace if exists)
        gdf.to_postgis(
            staging, self._engine, schema=schema,
            if_exists="replace", index=False,
        )

        # Deduplicate staging table — keep last row per conflict key
        # (ON CONFLICT cannot update the same row twice in one command)
        dedup_sql = text(f"""
            DELETE FROM {schema}.{staging} a
            USING {schema}.{staging} b
            WHERE a.ctid < b.ctid
            AND a.{conflict_column} = b.{conflict_column}
        """)  # noqa: S608
        with self._engine.connect() as conn:
            conn.execute(dedup_sql)
            conn.commit()

        cols = ", ".join(gdf.columns)
        set_clause = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in update_columns
        )
        set_clause += ", imported_at = now()"

        upsert_sql = text(f"""
            WITH upsert_result AS (
                INSERT INTO {schema}.{table} ({cols})
                SELECT {cols} FROM {schema}.{staging}
                ON CONFLICT ({conflict_column}) DO UPDATE
                SET {set_clause}
                RETURNING (xmax = 0) AS inserted
            )
            SELECT
                COUNT(*) FILTER (WHERE inserted) AS insert_count,
                COUNT(*) FILTER (WHERE NOT inserted) AS update_count
            FROM upsert_result
        """)  # noqa: S608

        with self._engine.connect() as conn:
            result = conn.execute(upsert_sql).fetchone()
            conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{staging}"))  # noqa: S608
            conn.commit()

        inserted = result[0] if result else 0
        updated = result[1] if result else 0
        logger.info(
            "Upserted %s.%s: %d inserted, %d updated",
            schema, table, inserted, updated,
        )
        return (inserted, updated)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O, always testable)
# ---------------------------------------------------------------------------


def _coerce_int_columns(
    gdf: gpd.GeoDataFrame,
    cols: list[str],
) -> gpd.GeoDataFrame:
    """Convert float columns to nullable Int64 for integer DB columns.

    ArcGIS GeoJSON returns all numbers as floats (e.g. 1.0 instead of 1).
    """

    for col in cols:
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce").astype("Int64")
    return gdf


def rename_and_prepare(
    gdf: gpd.GeoDataFrame,
    col_map: dict[str, str],
) -> gpd.GeoDataFrame:
    """Rename columns, keep only mapped columns + geometry, set CRS.

    Args:
        gdf: Source GeoDataFrame.
        col_map: Mapping of source column names to target column names.

    Returns:
        Cleaned GeoDataFrame with geom column in EPSG:4269.
    """
    gdf = gdf.rename(columns=col_map)
    keep = [c for c in col_map.values() if c in gdf.columns] + ["geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]
    gdf = gdf.rename_geometry("geom")
    return gdf.to_crs(STORAGE_CRS)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


class EtlPipeline:
    """Orchestrates the riparian buffer compliance ETL pipeline.

    Uses constructor injection for all I/O dependencies so each step
    can be tested with fake clients and writers.

    Args:
        client: Feature client for fetching geospatial data.
        writer: Spatial writer for persisting data to PostGIS.
    """

    def __init__(
        self,
        client: FeatureClient,
        writer: SpatialWriter,
    ) -> None:
        self._client = client
        self._writer = writer

    def _count_rows(self, schema: str, table: str) -> int:
        """Return the row count of a table (for pre-flight checks)."""
        return self._writer.count_rows(schema, table)

    # -- Bronze layer -------------------------------------------------------

    def load_watershed(self) -> None:
        """Load the San Juan Basin (HUC8 14080101) watershed boundary."""
        logger.info("Loading watershed boundary for HUC8 %s", HUC8_CODE)

        gdf = self._client.query(
            url=WATERSHED_URL,
            where=f"HUC8='{HUC8_CODE}'",
            out_fields="HUC8,NAME,AREASQKM,STATES",
        )
        if gdf.empty:
            raise RuntimeError(f"No watershed found for HUC8 {HUC8_CODE}")

        gdf = rename_and_prepare(gdf, {
            "HUC8": "huc8", "NAME": "name",
            "AREASQKM": "area_sq_km", "STATES": "states",
        })
        # gold.riparian_summary references bronze.watersheds via FK —
        # PostgreSQL TRUNCATE checks FK constraints even on empty tables,
        # so CASCADE is required here. This is safe: riparian_summary is
        # the only dependent and gets recalculated at the end of the pipeline.
        self._writer.truncate("bronze", "watersheds", cascade=True)
        self._writer.write(gdf, "watersheds", "bronze")
        logger.info("Finished loading watershed boundary")

    def load_nhdplus_layers(self) -> None:
        """Load NHDPlus V2.1 streams, waterbodies, and sinks.

        Uses the watershed bounding box as a spatial filter to limit
        results to the study area.
        """
        logger.info("Loading NHDPlus layers")
        envelope = self._writer.get_watershed_envelope(HUC8_CODE)

        self._load_layer(
            name="streams", schema="bronze",
            url=f"{NHDPLUS_URL}/{NHDPLUS_FLOWLINE_LAYER}",
            envelope=envelope, explode=True,
            col_map={
                "COMID": "comid", "GNIS_NAME": "gnis_name",
                "REACHCODE": "reach_code", "FTYPE": "ftype",
                "FCODE": "fcode", "StreamOrde": "stream_order",
                "LENGTHKM": "length_km",
            },
            int_cols=["comid", "fcode", "stream_order"],
        )
        self._load_layer(
            name="waterbodies", schema="bronze",
            url=f"{NHDPLUS_URL}/{NHDPLUS_WATERBODY_LAYER}",
            envelope=envelope, explode=True,
            col_map={
                "COMID": "comid", "GNIS_NAME": "gnis_name",
                "FTYPE": "ftype", "FCODE": "fcode",
                "AREASQKM": "area_sq_km",
            },
            int_cols=["comid", "fcode"],
        )
        # Sinks layer has a different schema (SINKID, PURPCODE, etc.)
        # and is not required for buffer/compliance analysis.
        try:
            self._load_layer(
                name="sinks", schema="bronze",
                url=f"{NHDPLUS_URL}/{NHDPLUS_SINK_LAYER}",
                envelope=envelope,
                col_map={
                    "SINKID": "comid", "PURPDESC": "gnis_name",
                    "PURPCODE": "ftype", "GridCode": "fcode",
                },
            )
        except Exception:
            logger.warning("Sinks layer could not be loaded — skipping (non-critical)")
        logger.info("Finished loading all NHDPlus layers")

    def _load_layer(
        self,
        name: str,
        schema: str,
        url: str,
        col_map: dict[str, str],
        envelope: dict[str, Any] | None = None,
        where: str = "1=1",
        explode: bool = False,
        int_cols: list[str] | None = None,
    ) -> None:
        """Fetch, transform, and write a single feature layer.

        Paginates through the ArcGIS REST API to load all features
        (the API caps responses at maxRecordCount, typically 2000).
        """
        logger.info("Loading %s", name)

        batches: list[gpd.GeoDataFrame] = []
        offset = 0
        while True:
            batch = self._client.query(
                url=url, where=where, geometry_filter=envelope,
                result_offset=offset,
                result_record_count=ARCGIS_BATCH_SIZE,
            )
            if batch.empty:
                break
            batches.append(batch)
            logger.info("Fetched %s batch: %d features (offset %d)", name, len(batch), offset)
            offset += ARCGIS_BATCH_SIZE
            if len(batch) < ARCGIS_BATCH_SIZE:
                break

        if not batches:
            logger.warning("No %s found in study area", name)
            return

    
        gdf = gpd.GeoDataFrame(pd.concat(batches, ignore_index=True), crs=batches[0].crs)

        gdf = rename_and_prepare(gdf, col_map)
        if int_cols:
            gdf = _coerce_int_columns(gdf, int_cols)
        if explode:
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)

        # Full load truncates and replaces — CASCADE is safe here because
        # all dependent silver/gold tables are regenerated by the pipeline.
        self._writer.truncate(schema, name, cascade=True)
        self._writer.write(gdf, name, schema)
        logger.info("Finished loading %d %s", len(gdf), name)

    def load_parcels(self) -> None:
        """Load Colorado parcels with pagination and field renaming.

        Paginates through the ArcGIS REST API in batches and applies
        the field renaming documented in CLAUDE.md:
        landUseDsc -> land_use_desc, landUseCde -> land_use_code,
        zoningDesc -> zoning_desc, owner -> owner_name,
        landAcres -> land_acres.
        """
        logger.info("Loading parcels with pagination")
        envelope = self._writer.get_watershed_envelope(HUC8_CODE)
        # CASCADE safe: parcel_compliance is regenerated by analyze_compliance()
        self._writer.truncate("bronze", "parcels", cascade=True)

        source_fields = ",".join(PARCEL_FIELD_MAP.keys())
        offset = 0
        total = 0
        seen_ids: set[str] = set()

        while True:
            gdf = self._client.query(
                url=PARCELS_URL,
                out_fields=source_fields,
                geometry_filter=envelope,
                result_offset=offset,
                result_record_count=ARCGIS_BATCH_SIZE,
            )
            if gdf.empty:
                break

            gdf = rename_and_prepare(gdf, PARCEL_FIELD_MAP)
            # Drop rows missing required parcel_id
            before = len(gdf)
            gdf = gdf.dropna(subset=["parcel_id"])
            if len(gdf) < before:
                logger.info("Dropped %d parcels with null parcel_id", before - len(gdf))
            # Deduplicate within batch and across batches
            gdf = gdf.drop_duplicates(subset=["parcel_id"], keep="first")
            gdf = gdf[~gdf["parcel_id"].isin(seen_ids)]
            if gdf.empty:
                continue
            seen_ids.update(gdf["parcel_id"].tolist())
            self._writer.write(gdf, "parcels", "bronze")

            batch_count = len(gdf)
            total += batch_count
            offset += ARCGIS_BATCH_SIZE
            logger.info(
                "Loaded parcel batch: %d (total: %d)", batch_count, total,
            )
            if batch_count < ARCGIS_BATCH_SIZE:
                break

        logger.info("Finished loading %d parcels", total)

    # -- Silver layer -------------------------------------------------------

    def generate_buffers(
        self,
        buffer_distance_m: float = DEFAULT_BUFFER_DISTANCE_M,
    ) -> None:
        """Generate riparian buffer polygons around stream centerlines.

        Uses ST_Buffer on geography type for meter-accurate distances.
        Default is 100 feet (30.48 m).

        Args:
            buffer_distance_m: Buffer width in meters.
        """
        logger.info(
            "Generating riparian buffers (%.1f m / %.0f ft)",
            buffer_distance_m,
            buffer_distance_m * 3.28084,
        )
        # Full regeneration: warn about NDVI loss, then CASCADE to clear
        # all dependent tables (parcel_compliance, vegetation_health).
        # PostgreSQL TRUNCATE checks FK constraints even on empty tables,
        # so CASCADE is required regardless of truncation order.
        ndvi_count = self._count_rows("silver", "vegetation_health")
        if ndvi_count > 0:
            logger.warning(
                "Full buffer regeneration will delete %d NDVI readings. "
                "Use './dev.sh --backup' beforehand or run incremental mode "
                "to preserve them.",
                ndvi_count,
            )
        self._writer.truncate("silver", "riparian_buffers", cascade=True)
        count = self._writer.execute(
            _GENERATE_BUFFERS_SQL,
            {"buffer_distance": buffer_distance_m},
        )
        logger.info("Generated %d riparian buffers", count)

    def analyze_compliance(self) -> None:
        """Flag parcels that encroach on riparian buffer zones.

        Uses bounding-box pre-filter (&&) before the expensive spatial
        intersection. Only records overlaps greater than 1 sq meter to
        exclude rounding artifacts.
        """
        logger.info("Analyzing parcel-buffer compliance")
        self._writer.truncate("silver", "parcel_compliance")
        count = self._writer.execute(_ANALYZE_COMPLIANCE_SQL)
        logger.info("Found %d compliance focus areas", count)

    # -- Gold layer ---------------------------------------------------------

    def calculate_summary(self) -> None:
        """Calculate compliance summary statistics per watershed.

        Aggregates stream lengths, buffer areas, and parcel compliance
        rates using CTEs. NDVI vegetation health fields are populated
        separately by update_summary_ndvi().
        """
        logger.info("Calculating compliance summary")
        self._writer.truncate("gold", "riparian_summary")
        count = self._writer.execute(_CALCULATE_SUMMARY_SQL)
        logger.info("Generated %d summary records", count)

    def update_summary_ndvi(self) -> None:
        """Update gold summary with aggregated NDVI health statistics.

        Uses the latest peak-growing reading per buffer to compute
        avg NDVI and health category percentages, then patches the
        existing gold.riparian_summary row.
        """
        logger.info("Updating gold summary with NDVI statistics")
        count = self._writer.execute(_UPDATE_SUMMARY_NDVI_SQL)
        logger.info("Updated %d summary records with NDVI stats", count)

    # -- Orchestration ------------------------------------------------------

    def run(self) -> None:
        """Run the full pipeline: bronze -> silver -> gold."""
        logger.info("Starting Riparian Buffer Compliance ETL pipeline")

        # Bronze -- raw data ingestion
        self.load_watershed()
        self.load_nhdplus_layers()
        self.load_parcels()

        # Silver -- spatial processing
        self.generate_buffers()
        self.analyze_compliance()

        # Gold -- aggregated analytics
        self.calculate_summary()

        logger.info("ETL pipeline completed successfully")

    # -- Incremental pipeline -----------------------------------------------

    def _load_layer_incremental(
        self,
        name: str,
        schema: str,
        url: str,
        col_map: dict[str, str],
        conflict_column: str,
        update_columns: list[str],
        envelope: dict[str, Any] | None = None,
        where: str = "1=1",
        explode: bool = False,
        int_cols: list[str] | None = None,
    ) -> LayerChangeResult:
        """Fetch, transform, and upsert a single feature layer.

        Paginates through the ArcGIS REST API to load all features
        (the API caps responses at maxRecordCount, typically 2000).

        Args:
            name: Layer/table name for logging.
            schema: Target database schema.
            url: ArcGIS REST endpoint URL.
            col_map: Source-to-target column name mapping.
            conflict_column: UNIQUE column for ON CONFLICT.
            update_columns: Columns to SET on conflict.
            envelope: Spatial bounding box filter.
            where: SQL WHERE clause.
            explode: Whether to explode multi-geometries.
            int_cols: Columns to coerce from float to Int64.

        Returns:
            LayerChangeResult with insert/update counts.
        """
        logger.info("Incremental load: %s", name)

        batches: list[gpd.GeoDataFrame] = []
        offset = 0
        while True:
            batch = self._client.query(
                url=url, where=where, geometry_filter=envelope,
                result_offset=offset,
                result_record_count=ARCGIS_BATCH_SIZE,
            )
            if batch.empty:
                break
            batches.append(batch)
            logger.info("Fetched %s batch: %d features (offset %d)", name, len(batch), offset)
            offset += ARCGIS_BATCH_SIZE
            if len(batch) < ARCGIS_BATCH_SIZE:
                break

        if not batches:
            logger.warning("No %s found in study area", name)
            return LayerChangeResult(name, 0, 0, 0)

    
        gdf = gpd.GeoDataFrame(pd.concat(batches, ignore_index=True), crs=batches[0].crs)

        gdf = rename_and_prepare(gdf, col_map)
        if int_cols:
            gdf = _coerce_int_columns(gdf, int_cols)
        if explode:
            gdf = gdf.explode(index_parts=False).reset_index(drop=True)

        inserted, updated = self._writer.upsert(
            gdf, name, schema, conflict_column, update_columns,
        )
        skipped = len(gdf) - inserted - updated
        return LayerChangeResult(name, inserted, updated, skipped)

    def load_nhdplus_layers_incremental(self) -> LayerChangeResult:
        """Incrementally upsert NHDPlus streams and waterbodies.

        Returns:
            Combined LayerChangeResult (has_changes if any layer changed).
        """
        logger.info("Incremental loading NHDPlus layers")
        envelope = self._writer.get_watershed_envelope(HUC8_CODE)

        streams = self._load_layer_incremental(
            name="streams", schema="bronze",
            url=f"{NHDPLUS_URL}/{NHDPLUS_FLOWLINE_LAYER}",
            envelope=envelope, explode=True,
            col_map={
                "COMID": "comid", "GNIS_NAME": "gnis_name",
                "REACHCODE": "reach_code", "FTYPE": "ftype",
                "FCODE": "fcode", "StreamOrde": "stream_order",
                "LENGTHKM": "length_km",
            },
            conflict_column="comid",
            update_columns=["gnis_name", "reach_code", "ftype",
                            "fcode", "stream_order", "length_km", "geom"],
            int_cols=["comid", "fcode", "stream_order"],
        )
        waterbodies = self._load_layer_incremental(
            name="waterbodies", schema="bronze",
            url=f"{NHDPLUS_URL}/{NHDPLUS_WATERBODY_LAYER}",
            envelope=envelope, explode=True,
            col_map={
                "COMID": "comid", "GNIS_NAME": "gnis_name",
                "FTYPE": "ftype", "FCODE": "fcode",
                "AREASQKM": "area_sq_km",
            },
            conflict_column="comid",
            update_columns=["gnis_name", "ftype", "fcode",
                            "area_sq_km", "geom"],
            int_cols=["comid", "fcode"],
        )
        total = LayerChangeResult(
            "nhdplus",
            streams.inserted + waterbodies.inserted,
            streams.updated + waterbodies.updated,
            streams.skipped + waterbodies.skipped,
        )
        logger.info("Finished incremental NHDPlus: %s", total)
        return total

    def load_parcels_incremental(self) -> LayerChangeResult:
        """Incrementally upsert Colorado parcels with pagination.

        Returns:
            LayerChangeResult with total insert/update counts.
        """
        logger.info("Incremental loading parcels")
        envelope = self._writer.get_watershed_envelope(HUC8_CODE)

        source_fields = ",".join(PARCEL_FIELD_MAP.keys())
        offset = 0
        total_inserted = 0
        total_updated = 0
        total_skipped = 0

        while True:
            gdf = self._client.query(
                url=PARCELS_URL,
                out_fields=source_fields,
                geometry_filter=envelope,
                result_offset=offset,
                result_record_count=ARCGIS_BATCH_SIZE,
            )
            if gdf.empty:
                break

            gdf = rename_and_prepare(gdf, PARCEL_FIELD_MAP)
            gdf = gdf.dropna(subset=["parcel_id"])
            if gdf.empty:
                offset += ARCGIS_BATCH_SIZE
                continue

            inserted, updated = self._writer.upsert(
                gdf, "parcels", "bronze",
                conflict_column="parcel_id",
                update_columns=["land_use_desc", "land_use_code",
                                "zoning_desc", "owner_name",
                                "land_acres", "geom"],
            )
            total_inserted += inserted
            total_updated += updated
            total_skipped += len(gdf) - inserted - updated

            offset += ARCGIS_BATCH_SIZE
            if len(gdf) < ARCGIS_BATCH_SIZE:
                break

        result = LayerChangeResult(
            "parcels", total_inserted, total_updated, total_skipped,
        )
        logger.info("Finished incremental parcels: %s", result)
        return result

    def run_incremental(self) -> tuple[bool, bool, bool]:
        """Run an incremental update: upsert bronze, smart-recompute silver/gold.

        Returns:
            Tuple of (streams_changed, parcels_changed, buffers_changed).
        """
        logger.info("Starting incremental ETL pipeline")

        # Bronze -- upsert (watershed always full refresh, only 1 record)
        self.load_watershed()
        nhdplus_result = self.load_nhdplus_layers_incremental()
        parcels_result = self.load_parcels_incremental()

        streams_changed = nhdplus_result.has_changes
        parcels_changed = parcels_result.has_changes
        buffers_changed = False

        # Silver -- recompute only if upstream changed
        if streams_changed:
            self.generate_buffers()
            buffers_changed = True

        if parcels_changed or buffers_changed:
            self.analyze_compliance()

        # Gold -- recompute after any silver changes
        if streams_changed or parcels_changed or buffers_changed:
            self.calculate_summary()
        else:
            logger.info("No bronze changes — skipping silver/gold recompute")

        logger.info(
            "Incremental ETL completed: streams_changed=%s, "
            "parcels_changed=%s, buffers_changed=%s",
            streams_changed, parcels_changed, buffers_changed,
        )
        return (streams_changed, parcels_changed, buffers_changed)


# ---------------------------------------------------------------------------
# SQL constants for silver/gold spatial processing
# ---------------------------------------------------------------------------

_GENERATE_BUFFERS_SQL = text("""
    INSERT INTO silver.riparian_buffers
        (stream_id, buffer_distance_m, area_sq_m, geom)
    SELECT
        s.id,
        :buffer_distance,
        ST_Area(ST_Buffer(s.geom::geography, :buffer_distance)),
        ST_SetSRID(
            ST_Buffer(s.geom::geography, :buffer_distance)::geometry,
            4269
        )
    FROM bronze.streams s
""")

# Bounding-box pre-filter (&&) before expensive ST_Intersects per convention
_ANALYZE_COMPLIANCE_SQL = text("""
    WITH intersections AS (
        SELECT
            p.id AS parcel_id,
            b.id AS buffer_id,
            b.area_sq_m AS buffer_area_sq_m,
            ST_Intersection(p.geom, b.geom) AS overlap_geom
        FROM bronze.parcels p
        JOIN silver.riparian_buffers b
            ON p.geom && b.geom
            AND ST_Intersects(p.geom, b.geom)
    )
    INSERT INTO silver.parcel_compliance (
        parcel_id, buffer_id, overlap_area_sq_m, overlap_pct,
        is_focus_area, focus_area_reason, geom
    )
    SELECT
        i.parcel_id,
        i.buffer_id,
        ST_Area(i.overlap_geom::geography),
        ST_Area(i.overlap_geom::geography)
            / NULLIF(i.buffer_area_sq_m, 0) * 100,
        TRUE,
        'Parcel overlaps riparian buffer zone',
        i.overlap_geom
    FROM intersections i
    WHERE ST_Area(i.overlap_geom::geography) > 1
""")

_CALCULATE_SUMMARY_SQL = text("""
    WITH stream_stats AS (
        SELECT
            w.id AS watershed_id,
            w.huc8,
            COALESCE(SUM(ST_Length(s.geom::geography)), 0)
                AS total_stream_length_m
        FROM bronze.watersheds w
        LEFT JOIN bronze.streams s
            ON s.geom && w.geom AND ST_Intersects(s.geom, w.geom)
        GROUP BY w.id, w.huc8
    ),
    buffer_stats AS (
        SELECT
            w.id AS watershed_id,
            COALESCE(SUM(b.area_sq_m), 0) AS total_buffer_area_sq_m
        FROM bronze.watersheds w
        LEFT JOIN bronze.streams s
            ON s.geom && w.geom AND ST_Intersects(s.geom, w.geom)
        LEFT JOIN silver.riparian_buffers b ON b.stream_id = s.id
        GROUP BY w.id
    ),
    parcel_stats AS (
        SELECT
            w.id AS watershed_id,
            COUNT(DISTINCT p.id) AS total_parcels,
            COUNT(DISTINCT CASE
                WHEN pc.is_focus_area THEN pc.parcel_id
            END) AS focus_area_parcels
        FROM bronze.watersheds w
        LEFT JOIN bronze.parcels p
            ON p.geom && w.geom AND ST_Intersects(p.geom, w.geom)
        LEFT JOIN silver.parcel_compliance pc
            ON pc.parcel_id = p.id AND pc.is_focus_area = TRUE
        GROUP BY w.id
    )
    INSERT INTO gold.riparian_summary (
        watershed_id, huc8, total_stream_length_m, total_buffer_area_sq_m,
        total_parcels, compliant_parcels, focus_area_parcels, compliance_pct
    )
    SELECT
        ss.watershed_id,
        ss.huc8,
        ss.total_stream_length_m,
        bs.total_buffer_area_sq_m,
        ps.total_parcels,
        ps.total_parcels - ps.focus_area_parcels,
        ps.focus_area_parcels,
        CASE
            WHEN ps.total_parcels > 0
            THEN (ps.total_parcels - ps.focus_area_parcels)::NUMERIC
                / ps.total_parcels * 100
            ELSE 100
        END
    FROM stream_stats ss
    JOIN buffer_stats bs ON bs.watershed_id = ss.watershed_id
    JOIN parcel_stats ps ON ps.watershed_id = ss.watershed_id
""")

_UPDATE_SUMMARY_NDVI_SQL = text("""
    UPDATE gold.riparian_summary rs SET
        avg_ndvi = agg.avg_ndvi,
        healthy_buffer_pct = agg.healthy_pct,
        degraded_buffer_pct = agg.degraded_pct,
        bare_buffer_pct = agg.bare_pct
    FROM (
        SELECT
            AVG(vh.mean_ndvi) AS avg_ndvi,
            COUNT(*) FILTER (WHERE vh.health_category = 'healthy') * 100.0
                / NULLIF(COUNT(*), 0) AS healthy_pct,
            COUNT(*) FILTER (WHERE vh.health_category = 'degraded') * 100.0
                / NULLIF(COUNT(*), 0) AS degraded_pct,
            COUNT(*) FILTER (WHERE vh.health_category = 'bare') * 100.0
                / NULLIF(COUNT(*), 0) AS bare_pct
        FROM silver.vegetation_health vh
        WHERE vh.id IN (
            SELECT DISTINCT ON (buffer_id) id
            FROM silver.vegetation_health
            WHERE season_context = 'peak_growing'
            ORDER BY buffer_id, acquisition_date DESC
        )
    ) agg
    WHERE rs.id = (SELECT MAX(id) FROM gold.riparian_summary)
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_database_url() -> str:
    """Resolve the PostgreSQL connection URL from Aspire or env vars.

    Aspire injects several env vars; prefer the URI form. Fall back to
    converting the ADO.NET-style ConnectionStrings__ripariandb.
    """
    # 1. Aspire URI (already a proper postgresql:// URL)
    url = os.environ.get("RIPARIANDB_URI") or os.environ.get("DATABASE_URL")
    if url:
        return url

    # 2. ADO.NET connection string → convert to SQLAlchemy URL
    ado = os.environ.get("ConnectionStrings__ripariandb")
    if ado:
        parts: dict[str, str] = {}
        for part in ado.split(";"):
            if "=" in part:
                key, val = part.split("=", 1)
                parts[key.strip().lower()] = val.strip()
        host = parts.get("host", "localhost")
        port = parts.get("port", "5432")
        user = parts.get("username", "postgres")
        password = parts.get("password", "")
        database = parts.get("database", "ripariandb")
        from urllib.parse import quote_plus
        return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"

    return ""


def main() -> None:
    """Create real dependencies and run the pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    url = _resolve_database_url()
    if not url:
        logger.error(
            "No database URL found. Set RIPARIANDB_URI, DATABASE_URL, "
            "or ConnectionStrings__ripariandb"
        )
        sys.exit(1)

    logger.info("Connecting to database...")
    engine = create_engine(url)
    pipeline = EtlPipeline(
        client=ArcGISFeatureClient(),
        writer=PostGISWriter(engine),
    )
    pipeline.run()


if __name__ == "__main__":
    main()
