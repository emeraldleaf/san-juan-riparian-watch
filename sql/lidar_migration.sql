-- ---------------------------------------------------------------------------
-- Phase 5: LiDAR Canopy Height — Silver layer table
-- ---------------------------------------------------------------------------
-- Run against the riparian-poc PostGIS database.
--
-- Creates:
--   silver.buffer_canopy   – per-buffer canopy height statistics from 3DEP LiDAR

-- Ensure silver schema exists (idempotent)
CREATE SCHEMA IF NOT EXISTS silver;

-- Silver: LiDAR-derived canopy metrics per buffer
CREATE TABLE IF NOT EXISTS silver.buffer_canopy (
    id               SERIAL PRIMARY KEY,
    buffer_id        INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    mean_height_m    NUMERIC(6, 2),
    max_height_m     NUMERIC(6, 2),
    p95_height_m     NUMERIC(6, 2),
    canopy_cover_pct NUMERIC(5, 2),
    height_std_dev   NUMERIC(6, 2),
    processed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_buffer_canopy_buffer UNIQUE (buffer_id)
);

CREATE INDEX IF NOT EXISTS idx_buffer_canopy_buffer_id
    ON silver.buffer_canopy (buffer_id);
