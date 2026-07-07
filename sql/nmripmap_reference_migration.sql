-- ============================================================================
-- Reference-riparian sources in silver.riparian_extent
-- ----------------------------------------------------------------------------
-- Additive migration (does NOT modify create_schemas.sql). Widens the method
-- CHECK so authoritative reference maps (NMRipMap for NM, CO-RIP for CO) can be
-- stored + served through the SAME /api/riparian/extent endpoint as the model
-- predictions ('rf' / 'olmoearth'). Lets the frontend overlay ground-truth vs
-- the learned extent for comparison. See docs/specs/2026-07-03-stage1-*.md.
-- ============================================================================

ALTER TABLE silver.riparian_extent
    DROP CONSTRAINT IF EXISTS ck_riparian_extent_method;

ALTER TABLE silver.riparian_extent
    ADD CONSTRAINT ck_riparian_extent_method
    CHECK (method = ANY (ARRAY['rf', 'olmoearth', 'nmripmap', 'corip']));

COMMENT ON COLUMN silver.riparian_extent.method IS
    'Source of the riparian-extent polygons: rf / olmoearth (learned predictions) '
    'or nmripmap / corip (authoritative reference maps).';
