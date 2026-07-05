-- NWI Wetlands + SMP Dataset Integration Migration
-- Adds: NWI wetlands (bronze), buffer-wetland intersection (silver),
--        and future SMP dataset tables
-- Safe to run multiple times (IF NOT EXISTS patterns)

BEGIN;

-- ============================================================
-- BRONZE: NWI wetland polygons from FWS ArcGIS REST service
-- ============================================================

CREATE TABLE IF NOT EXISTS bronze.nwi_wetlands (
    id              SERIAL PRIMARY KEY,
    wetland_type    TEXT,
    cowardin_code   TEXT,
    acres           NUMERIC(12, 4),
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nwi_wetlands_geom
    ON bronze.nwi_wetlands USING gist (geom);

-- ============================================================
-- SILVER: Buffer-wetland spatial intersection
-- ============================================================

CREATE TABLE IF NOT EXISTS silver.buffer_wetlands (
    id                    SERIAL PRIMARY KEY,
    buffer_id             INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    wetland_id            INTEGER NOT NULL REFERENCES bronze.nwi_wetlands(id),
    overlap_area_sq_m     NUMERIC(14, 2),
    wetland_pct_of_buffer NUMERIC(5, 2),
    wetland_type          TEXT,
    cowardin_code         TEXT,
    processed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buffer_wetlands_buffer_id
    ON silver.buffer_wetlands (buffer_id);
CREATE INDEX IF NOT EXISTS idx_buffer_wetlands_wetland_id
    ON silver.buffer_wetlands (wetland_id);

COMMIT;
