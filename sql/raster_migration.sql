-- Raster Dataset Integration Migration (NLCD + LANDFIRE)
-- Adds: buffer_land_cover (silver), buffer_vegetation_structure (silver)
-- Safe to run multiple times (IF NOT EXISTS patterns)

BEGIN;

-- ============================================================
-- SILVER: NLCD land cover class distribution per buffer
-- ============================================================

CREATE TABLE IF NOT EXISTS silver.buffer_land_cover (
    id                SERIAL PRIMARY KEY,
    buffer_id         INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    nlcd_class        INTEGER NOT NULL,
    nlcd_description  TEXT NOT NULL,
    pixel_count       INTEGER NOT NULL,
    area_pct          NUMERIC(5, 2),
    is_natural        BOOLEAN NOT NULL DEFAULT FALSE,
    acquisition_year  INTEGER,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buffer_land_cover_buffer_id
    ON silver.buffer_land_cover (buffer_id);

-- ============================================================
-- SILVER: LANDFIRE vegetation structure per buffer
-- ============================================================

CREATE TABLE IF NOT EXISTS silver.buffer_vegetation_structure (
    id                SERIAL PRIMARY KEY,
    buffer_id         INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    evt_code          INTEGER,
    evt_name          TEXT,
    evh_class         TEXT,
    mean_height_m     NUMERIC(6, 2),
    dominant_lifeform TEXT,
    pixel_count       INTEGER,
    area_pct          NUMERIC(5, 2),
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buffer_veg_structure_buffer_id
    ON silver.buffer_vegetation_structure (buffer_id);

COMMIT;
