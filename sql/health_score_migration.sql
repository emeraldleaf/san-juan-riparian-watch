-- Composite Health Score Migration
-- Adds: gold.buffer_health_score (SMP 80/10/10 composite per buffer)
-- Safe to run multiple times (IF NOT EXISTS pattern)

BEGIN;

-- ============================================================
-- GOLD: SMP-aligned composite riparian health score per buffer
-- 80% Vegetation Structure / 10% Connectivity / 10% Contributing Area
-- ============================================================

CREATE TABLE IF NOT EXISTS gold.buffer_health_score (
    id                          SERIAL PRIMARY KEY,
    buffer_id                   INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),

    -- Vegetation Structure sub-scores (0.0 – 10.0 scale)
    ndvi_score                  NUMERIC(5, 2),
    vertical_complexity_score   NUMERIC(5, 2),
    species_composition_score   NUMERIC(5, 2),
    shrub_layer_score           NUMERIC(5, 2),
    patchiness_score            NUMERIC(5, 2),
    native_regeneration_score   NUMERIC(5, 2),
    native_cover_score          NUMERIC(5, 2),

    -- Weighted category scores (0.0 – 100.0 scale)
    vegetation_structure_score  NUMERIC(5, 2),
    connectivity_score          NUMERIC(5, 2),
    contributing_area_score     NUMERIC(5, 2),

    -- Composite
    composite_score             NUMERIC(5, 2),
    score_grade                 CHAR(1) CHECK (score_grade IN ('A','B','C','D','F')),
    scored_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_buffer_health_score_buffer_id
    ON gold.buffer_health_score (buffer_id);
CREATE INDEX IF NOT EXISTS idx_buffer_health_score_grade
    ON gold.buffer_health_score (score_grade);

-- Add composite score columns to riparian_summary if not present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'gold'
        AND   table_name   = 'riparian_summary'
        AND   column_name  = 'avg_composite_score'
    ) THEN
        ALTER TABLE gold.riparian_summary
            ADD COLUMN avg_composite_score NUMERIC(5, 2),
            ADD COLUMN grade_a_pct NUMERIC(5, 2),
            ADD COLUMN grade_b_pct NUMERIC(5, 2),
            ADD COLUMN grade_c_pct NUMERIC(5, 2),
            ADD COLUMN grade_d_pct NUMERIC(5, 2),
            ADD COLUMN grade_f_pct NUMERIC(5, 2);
    END IF;
END $$;

COMMIT;
