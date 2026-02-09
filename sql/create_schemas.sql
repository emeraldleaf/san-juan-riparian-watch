-- Riparian Buffer Compliance POC — Schema Source of Truth
-- Medallion architecture: bronze → silver → gold
-- All geometry stored in EPSG:4269 (NAD83)
-- Cast to geography for distance/area calculations

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- BRONZE SCHEMA — Raw ingested data, minimal transformation
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- NHDPlus V2.1 stream centerlines
CREATE TABLE bronze.streams (
    id              SERIAL PRIMARY KEY,
    comid           BIGINT NOT NULL UNIQUE,
    gnis_name       TEXT,
    reach_code      VARCHAR(14),
    ftype           TEXT,
    fcode           INTEGER,
    stream_order    INTEGER,
    length_km       NUMERIC(12, 4),
    geom            geometry(LineString, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_streams_geom ON bronze.streams USING gist (geom);
CREATE INDEX idx_streams_comid ON bronze.streams (comid);

-- NHDPlus V2.1 waterbodies
CREATE TABLE bronze.waterbodies (
    id              SERIAL PRIMARY KEY,
    comid           BIGINT NOT NULL UNIQUE,
    gnis_name       TEXT,
    ftype           TEXT,
    fcode           INTEGER,
    area_sq_km      NUMERIC(12, 4),
    geom            geometry(Polygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_waterbodies_geom ON bronze.waterbodies USING gist (geom);
CREATE INDEX idx_waterbodies_comid ON bronze.waterbodies (comid);

-- NHDPlus V2.1 sinks
CREATE TABLE bronze.sinks (
    id              SERIAL PRIMARY KEY,
    comid           BIGINT NOT NULL UNIQUE,
    gnis_name       TEXT,
    ftype           TEXT,
    fcode           INTEGER,
    geom            geometry(Point, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sinks_geom ON bronze.sinks USING gist (geom);
CREATE INDEX idx_sinks_comid ON bronze.sinks (comid);

-- Colorado Public Parcels
-- Field mapping applied during ETL:
--   parcel_id → parcel_id, landUseDsc → land_use_desc,
--   landUseCde → land_use_code, zoningDesc → zoning_desc,
--   owner → owner_name, landAcres → land_acres
CREATE TABLE bronze.parcels (
    id              SERIAL PRIMARY KEY,
    parcel_id       TEXT NOT NULL,
    land_use_desc   TEXT,
    land_use_code   TEXT,
    zoning_desc     TEXT,
    owner_name      TEXT,
    land_acres      NUMERIC(12, 4),
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_parcels_geom ON bronze.parcels USING gist (geom);
CREATE INDEX idx_parcels_parcel_id ON bronze.parcels (parcel_id);

-- USDA Watersheds (HUC boundaries)
CREATE TABLE bronze.watersheds (
    id              SERIAL PRIMARY KEY,
    huc8            VARCHAR(8) NOT NULL,
    name            TEXT,
    area_sq_km      NUMERIC(12, 4),
    states          TEXT,
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_watersheds_geom ON bronze.watersheds USING gist (geom);
CREATE INDEX idx_watersheds_huc8 ON bronze.watersheds (huc8);

-- ============================================================
-- SILVER SCHEMA — Spatial processing, compliance, NDVI scoring
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- Riparian buffer polygons generated from stream centerlines
-- Buffer distance in meters via ST_Buffer(geom::geography, meters)
CREATE TABLE silver.riparian_buffers (
    id              SERIAL PRIMARY KEY,
    stream_id       INTEGER NOT NULL REFERENCES bronze.streams(id),
    buffer_distance_m NUMERIC(8, 2) NOT NULL,
    area_sq_m       NUMERIC(14, 2),
    geom            geometry(Polygon, 4269) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_riparian_buffers_geom ON silver.riparian_buffers USING gist (geom);
CREATE INDEX idx_riparian_buffers_stream_id ON silver.riparian_buffers (stream_id);

-- Parcel-buffer intersection and compliance flagging
CREATE TABLE silver.parcel_compliance (
    id              SERIAL PRIMARY KEY,
    parcel_id       INTEGER NOT NULL REFERENCES bronze.parcels(id),
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    overlap_area_sq_m   NUMERIC(14, 2),
    overlap_pct         NUMERIC(5, 2),
    is_focus_area       BOOLEAN NOT NULL DEFAULT FALSE,
    focus_area_reason   TEXT,
    geom                geometry(Geometry, 4269),
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_parcel_compliance_geom ON silver.parcel_compliance USING gist (geom);
CREATE INDEX idx_parcel_compliance_parcel_id ON silver.parcel_compliance (parcel_id);
CREATE INDEX idx_parcel_compliance_buffer_id ON silver.parcel_compliance (buffer_id);
CREATE INDEX idx_parcel_compliance_focus_area ON silver.parcel_compliance (is_focus_area)
    WHERE is_focus_area = TRUE;

-- NDVI vegetation health scoring per buffer
-- Health categories: healthy (>0.6), degraded (0.3–0.6), bare (<0.3), dormant (dormant season)
CREATE TABLE silver.vegetation_health (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    acquisition_date DATE NOT NULL,
    mean_ndvi       NUMERIC(5, 4),
    min_ndvi        NUMERIC(5, 4),
    max_ndvi        NUMERIC(5, 4),
    health_category TEXT NOT NULL CHECK (health_category IN ('healthy', 'degraded', 'bare', 'dormant')),
    season_context  TEXT NOT NULL,
    satellite       TEXT DEFAULT 'Sentinel-2',
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vegetation_health_buffer_id ON silver.vegetation_health (buffer_id);
CREATE INDEX idx_vegetation_health_date ON silver.vegetation_health (acquisition_date);

-- ============================================================
-- GOLD SCHEMA — Aggregated analytics, summary by watershed
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- Compliance summary statistics per watershed
CREATE TABLE gold.riparian_summary (
    id                      SERIAL PRIMARY KEY,
    watershed_id            INTEGER NOT NULL REFERENCES bronze.watersheds(id),
    huc8                    VARCHAR(8) NOT NULL,
    total_stream_length_m   NUMERIC(14, 2),
    total_buffer_area_sq_m  NUMERIC(14, 2),
    total_parcels           INTEGER NOT NULL DEFAULT 0,
    compliant_parcels       INTEGER NOT NULL DEFAULT 0,
    focus_area_parcels      INTEGER NOT NULL DEFAULT 0,
    compliance_pct          NUMERIC(5, 2),
    avg_ndvi                NUMERIC(5, 4),
    healthy_buffer_pct      NUMERIC(5, 2),
    degraded_buffer_pct     NUMERIC(5, 2),
    bare_buffer_pct         NUMERIC(5, 2),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_riparian_summary_watershed_id ON gold.riparian_summary (watershed_id);
CREATE INDEX idx_riparian_summary_huc8 ON gold.riparian_summary (huc8);

COMMIT;
