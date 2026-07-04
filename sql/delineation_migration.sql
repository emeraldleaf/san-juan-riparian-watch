-- ============================================================================
-- Stage 1: Riparian extent delineation
-- ----------------------------------------------------------------------------
-- Additive migration (does NOT modify create_schemas.sql). Adds:
--   bronze.riparian_training_samples  weak-labeled points for reproducible training
--   silver.riparian_extent            per-method delineation results (grid cells)
--
-- Weak labels come from the agreement of maps already ingested (LANDFIRE EVT
-- riparian ∧ NLCD woody/emergent wetlands ∧ NWI). See CONTEXT.md "Weak labels".
-- Storage CRS is EPSG:4269 (NAD83) throughout. See CLAUDE.md "Spatial Data".
-- ============================================================================

-- ----------------------------------------------------------------------------
-- bronze.riparian_training_samples
-- Persisted so a training run is reproducible and the validation split is
-- auditable. One row per sampled pixel/point over the study-area grid.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.riparian_training_samples (
    id              BIGSERIAL PRIMARY KEY,
    label           BOOLEAN     NOT NULL,          -- weak label: riparian (true) / not
    label_source    TEXT        NOT NULL,          -- e.g. 'landfire+nlcd+nwi:agreement'
    landfire_hit    BOOLEAN     NOT NULL DEFAULT FALSE,
    nlcd_hit        BOOLEAN     NOT NULL DEFAULT FALSE,
    nwi_hit         BOOLEAN     NOT NULL DEFAULT FALSE,
    agreement_count SMALLINT    NOT NULL DEFAULT 0, -- 0..3 sources agreeing on riparian
    spatial_fold    SMALLINT,                       -- spatial-CV block id (assigned at train time)
    geom            geometry(Point, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_riparian_training_samples_geom
    ON bronze.riparian_training_samples USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_riparian_training_samples_fold
    ON bronze.riparian_training_samples (spatial_fold);

COMMENT ON TABLE bronze.riparian_training_samples IS
    'Weak-labeled samples for Stage-1 riparian delineation. Label = agreement of '
    'LANDFIRE EVT riparian / NLCD woody-wetland / NWI. spatial_fold blocks are '
    'assigned at train time for spatial cross-validation (random splits leak due '
    'to spatial autocorrelation).';

-- ----------------------------------------------------------------------------
-- silver.riparian_extent
-- Delineation results, one row per grid cell per method. Two methods co-exist
-- (method = 'rf' | 'olmoearth') so they can be diffed over the same AOI.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS silver.riparian_extent (
    id                   BIGSERIAL PRIMARY KEY,
    method               TEXT        NOT NULL,      -- 'rf' | 'olmoearth'
    model_version        TEXT        NOT NULL,
    is_riparian          BOOLEAN     NOT NULL,
    riparian_probability NUMERIC(5, 4) NOT NULL,    -- 0.0000 .. 1.0000
    cell_size_m          NUMERIC(6, 2) NOT NULL,    -- native pixel size, e.g. 10.00
    geom                 geometry(Polygon, 4269) NOT NULL,
    processed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_riparian_extent_method
        CHECK (method IN ('rf', 'olmoearth')),
    CONSTRAINT ck_riparian_extent_probability
        CHECK (riparian_probability >= 0 AND riparian_probability <= 1)
);

CREATE INDEX IF NOT EXISTS idx_riparian_extent_geom
    ON silver.riparian_extent USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_riparian_extent_method
    ON silver.riparian_extent (method, model_version);

COMMENT ON TABLE silver.riparian_extent IS
    'Stage-1 riparian extent predictions. One row per grid cell per method. '
    'method rf = RF/XGBoost baseline on multitemporal features; method olmoearth '
    '= OlmoEarth foundation-model embeddings. Compared head-to-head. See '
    'docs/decisions/2026-07-03-delineation-over-hydrology-buffers.md.';

-- ----------------------------------------------------------------------------
-- HUC12 tiling (added 2026-07-03b): the AOI is the San Juan River HUC watershed,
-- processed per HUC12 subwatershed (restartable tiles). Each run is scoped to a
-- huc12 so tiles do not overwrite each other. Idempotent ALTERs.
-- ----------------------------------------------------------------------------
ALTER TABLE silver.riparian_extent
    ADD COLUMN IF NOT EXISTS huc12 TEXT;
ALTER TABLE bronze.riparian_training_samples
    ADD COLUMN IF NOT EXISTS huc12 TEXT;

CREATE INDEX IF NOT EXISTS idx_riparian_extent_huc12
    ON silver.riparian_extent (huc12);
CREATE INDEX IF NOT EXISTS idx_riparian_training_samples_huc12
    ON bronze.riparian_training_samples (huc12);
