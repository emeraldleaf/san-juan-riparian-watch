-- ============================================================================
-- Per-reach riparian outputs (network-first Stage-1 product)
-- ----------------------------------------------------------------------------
-- Additive migration. Adds:
--   bronze.nhd_flowlines   raw NHD flowlines per HUC12 tile (from The National Map)
--   gold.reach_riparian    NHD flowlines split into ~250 m reaches, each scored
--                          with %riparian_cover from silver.riparian_extent
--
-- This is the manager-facing product: "which reaches are riparian / degrading",
-- interpretable along the river network. Storage CRS EPSG:4269. See CLAUDE.md.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- bronze.nhd_flowlines
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.nhd_flowlines (
    id            BIGSERIAL PRIMARY KEY,
    permanent_id  TEXT,
    gnis_name     TEXT,
    fcode         INTEGER,
    huc12         TEXT,
    geom          geometry(Geometry, 4269) NOT NULL,  -- Line/MultiLine as returned
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nhd_flowlines_geom
    ON bronze.nhd_flowlines USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_nhd_flowlines_huc12
    ON bronze.nhd_flowlines (huc12);

COMMENT ON TABLE bronze.nhd_flowlines IS
    'Raw NHD flowlines (National Map Large Scale) per HUC12 tile, for reach '
    'segmentation of the network-first riparian product.';

-- ----------------------------------------------------------------------------
-- gold.reach_riparian
-- One row per ~250 m reach: %riparian_cover within a corridor buffer.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.reach_riparian (
    id                 BIGSERIAL PRIMARY KEY,
    permanent_id       TEXT,                    -- source NHD flowline
    gnis_name          TEXT,
    huc12              TEXT,
    reach_index        INTEGER NOT NULL,        -- 0-based reach along the flowline
    method             TEXT    NOT NULL,        -- delineation method scored ('rf' | 'olmoearth')
    length_m           NUMERIC(8, 2) NOT NULL,
    corridor_m         NUMERIC(6, 2) NOT NULL,  -- half-width buffer used for cover
    riparian_cover_pct NUMERIC(5, 2) NOT NULL,  -- 0.00 .. 100.00
    geom               geometry(LineString, 4269) NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_reach_cover_pct
        CHECK (riparian_cover_pct >= 0 AND riparian_cover_pct <= 100)
);

CREATE INDEX IF NOT EXISTS idx_reach_riparian_geom
    ON gold.reach_riparian USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_reach_riparian_huc12
    ON gold.reach_riparian (huc12, method);

COMMENT ON TABLE gold.reach_riparian IS
    'NHD flowlines split into ~250 m reaches, each scored with %riparian_cover '
    'from silver.riparian_extent within a corridor buffer. The manager-facing '
    'network-first product (prioritize reaches by cover / later by trend).';
