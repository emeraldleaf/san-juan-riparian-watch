-- SSURGO Soils Migration
-- Adds: bronze.ssurgo_soils (raw map unit polygons with hydric data)
--        silver.buffer_soils (buffer-soil spatial intersection)
-- Safe to run multiple times (IF NOT EXISTS patterns)

BEGIN;

-- ============================================================
-- BRONZE: SSURGO soil map unit polygons from NRCS SDM WFS + REST
-- ============================================================

CREATE TABLE IF NOT EXISTS bronze.ssurgo_soils (
    id              SERIAL PRIMARY KEY,
    mukey           TEXT NOT NULL UNIQUE,
    musym           TEXT,
    muname          TEXT,
    hydric_rating   TEXT,
    hydric_pct      NUMERIC(5, 2),
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ssurgo_soils_geom
    ON bronze.ssurgo_soils USING gist (geom);
CREATE INDEX IF NOT EXISTS idx_ssurgo_soils_mukey
    ON bronze.ssurgo_soils (mukey);

-- ============================================================
-- SILVER: Buffer-soil spatial intersection
-- ============================================================

CREATE TABLE IF NOT EXISTS silver.buffer_soils (
    id                    SERIAL PRIMARY KEY,
    buffer_id             INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    soil_id               INTEGER NOT NULL REFERENCES bronze.ssurgo_soils(id),
    overlap_area_sq_m     NUMERIC(14, 2),
    soil_pct_of_buffer    NUMERIC(5, 2),
    hydric_rating         TEXT,
    hydric_pct            NUMERIC(5, 2),
    muname                TEXT,
    processed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buffer_soils_buffer_id
    ON silver.buffer_soils (buffer_id);
CREATE INDEX IF NOT EXISTS idx_buffer_soils_soil_id
    ON silver.buffer_soils (soil_id);

COMMIT;
