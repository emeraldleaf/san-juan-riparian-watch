-- Incremental Update System Migration
-- Adds: meta.etl_runs tracking table, unique constraints for upsert support
-- Safe to run multiple times (IF NOT EXISTS / IF NOT EXISTS patterns)

BEGIN;

-- ============================================================
-- META SCHEMA — Operational metadata (outside medallion flow)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.etl_runs (
    id                  SERIAL PRIMARY KEY,
    run_type            TEXT NOT NULL
                        CHECK (run_type IN ('full', 'incremental', 'ndvi', 'all')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'failed')),
    records_inserted    INTEGER NOT NULL DEFAULT 0,
    records_updated     INTEGER NOT NULL DEFAULT 0,
    records_skipped     INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT,
    streams_changed     BOOLEAN NOT NULL DEFAULT FALSE,
    parcels_changed     BOOLEAN NOT NULL DEFAULT FALSE,
    buffers_changed     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_etl_runs_status
    ON meta.etl_runs (status);
CREATE INDEX IF NOT EXISTS idx_etl_runs_started
    ON meta.etl_runs (started_at DESC);

-- ============================================================
-- Unique constraints required for upsert (ON CONFLICT) support
-- ============================================================

-- Deduplicate parcels before adding constraint (safe no-op if no dupes)
DELETE FROM bronze.parcels p
WHERE p.id NOT IN (
    SELECT MIN(id) FROM bronze.parcels GROUP BY parcel_id
);

-- Parcel upsert key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_parcels_parcel_id'
    ) THEN
        ALTER TABLE bronze.parcels
            ADD CONSTRAINT uq_parcels_parcel_id UNIQUE (parcel_id);
    END IF;
END $$;

-- Vegetation health deduplication key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_vegetation_health_buffer_date_sat'
    ) THEN
        ALTER TABLE silver.vegetation_health
            ADD CONSTRAINT uq_vegetation_health_buffer_date_sat
            UNIQUE (buffer_id, acquisition_date, satellite);
    END IF;
END $$;

COMMIT;
