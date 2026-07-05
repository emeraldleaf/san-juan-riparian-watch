-- ============================================================================
-- Document Intelligence: geospatial link tables
-- ----------------------------------------------------------------------------
-- Additive migration (does NOT modify create_schemas.sql). Adds the `docs`
-- schema that owns the GEOSPATIAL half of the document-intelligence subsystem.
--
-- Split of concerns (see docs/decisions/2026-07-04-document-intelligence-subsystem.md):
--   * Qdrant  = semantic store (chunk text, embeddings, retrieval, rerank, CRAG)
--   * PostGIS = geo link store (this file) so map-click reverse lookup is a fast
--               spatial join against layers we already have (bronze.nhd_flowlines,
--               gold.reach_riparian, HUC12). Cross-referenced to Qdrant by chunk_id.
--
-- Storage CRS is EPSG:4269 (NAD83) throughout; ::geography for distance/area.
-- See CLAUDE.md "Spatial Data" + "Medallion Architecture" (docs = its own lane).
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS docs;

-- ----------------------------------------------------------------------------
-- docs.documents
-- One row per ingested source document (PDF or readable web-page snapshot).
-- Provenance columns (source_url, sha256, retrieved_at) make every citation
-- traceable and every ingest reproducible from the in-repo seed list.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS docs.documents (
    id            BIGSERIAL PRIMARY KEY,
    external_id   TEXT        NOT NULL UNIQUE,     -- stable seed-list id (e.g. 'sjrip-bassett-2015')
    title         TEXT        NOT NULL,
    authors       TEXT,
    year          SMALLINT,
    agency        TEXT,                            -- e.g. 'SJRIP', 'USGS', 'EPA', 'NMED', 'USBR'
    doc_type      TEXT        NOT NULL,            -- plan|report|paper|minutes|metadata|webpage
    source_url    TEXT        NOT NULL,
    license       TEXT,                            -- e.g. 'public-domain-us-gov', 'unknown'
    sha256        TEXT,                            -- content hash of the fetched artifact
    page_count    INTEGER,
    retrieved_at  TIMESTAMPTZ,
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_docs_documents_agency ON docs.documents (agency);
CREATE INDEX IF NOT EXISTS idx_docs_documents_year   ON docs.documents (year);

COMMENT ON TABLE docs.documents IS
    'Ingested watershed source documents (PDF / web snapshot). Chunk TEXT + '
    'embeddings live in Qdrant; this table holds provenance + is the parent of '
    'docs.chunk_geo_mentions. See docs/specs/2026-07-04-document-intelligence-rag.md.';

-- ----------------------------------------------------------------------------
-- docs.chunk_geo_mentions
-- One row per (chunk, geographic mention). Written at INGEST time by the
-- geo-tagging stage so the map-click reverse lookup ("docs for this area") is a
-- deterministic spatial join, not an LLM call. chunk_id references the Qdrant
-- point id (kept as TEXT to avoid coupling PostGIS to Qdrant's id scheme).
--
-- The LLM proposes free-form mention_text + a type guess; the deterministic
-- resolver fills resolved_kind / resolved_ref / geom (LLM never emits geometry).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS docs.chunk_geo_mentions (
    id             BIGSERIAL PRIMARY KEY,
    chunk_id       TEXT        NOT NULL,           -- Qdrant point id for the source chunk
    doc_id         BIGINT      NOT NULL REFERENCES docs.documents (id) ON DELETE CASCADE,
    page_start     INTEGER,                        -- carried from the chunk for citation anchoring
    page_end       INTEGER,
    mention_text   TEXT        NOT NULL,           -- free-form, as written (e.g. 'Animas River near Farmington')
    mention_type   TEXT        NOT NULL,           -- river|reservoir|huc|town|reach|place|coord|bbox
    confidence     NUMERIC(4,3),                   -- extractor confidence 0..1
    resolved_kind  TEXT,                           -- huc12|huc8|nhd_flowline|reach|gnis|null (unresolved)
    resolved_ref   TEXT,                           -- e.g. 'huc12=140801051001', 'gnis=Animas River'
    geom           geometry(Geometry, 4269),       -- resolved geometry (null while unresolved)
    imported_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunk_geo_mentions_geom
    ON docs.chunk_geo_mentions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_chunk_geo_mentions_doc
    ON docs.chunk_geo_mentions (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunk_geo_mentions_chunk
    ON docs.chunk_geo_mentions (chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_geo_mentions_resolved_ref
    ON docs.chunk_geo_mentions (resolved_ref);

COMMENT ON TABLE docs.chunk_geo_mentions IS
    'Geographic mentions extracted from document chunks, resolved to spatial keys '
    'against bronze.nhd_flowlines / gold.reach_riparian / HUC12. Powers the '
    'map-click -> docs reverse lookup as a GiST spatial join. geom is EPSG:4269.';
