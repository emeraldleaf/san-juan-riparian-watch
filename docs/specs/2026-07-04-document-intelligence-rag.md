# Feature spec — Document Intelligence: RAG Q&A + map-linked geo citations

**Produced by `/feature-spec` · 2026-07-04 · feeds the encoding loop**
Related: [Stage-1 delineation spec](2026-07-03-stage1-riparian-delineation.md),
[Stage-3 annual change spec](2026-07-04-stage3-annual-change.md).

A second surface over the same San Juan AOI: a **document-intelligence layer** that answers
questions with citations over a corpus of published watershed documents, and links its answers
to geography on the existing riparian map. The EO pipeline shows *where / how much*; this shows
*why*, grounded in the literature.

## Harness decision (the load-bearing one)

**Do not build a RAG system from scratch. Fork the existing "Re-find Catalog" production RAG**
(`/Users/joshuadell/Dev/AI Course/my-capstone-rag/production-app`) as the harness and re-point
it at the watershed corpus. That system already ships, production-grade:

- **Haystack 2.0 + Qdrant** ingestion / hybrid retrieval / reranking, table-aware + adaptive
  chunking, PyPDF2 fast-path + Docling OCR extraction.
- A **10-stage pipeline** (`services/rag_pipeline.py`): InputGuard → Memory → Cache → Router →
  Retrieval → **CRAG** (`document_grader.py`) → Adaptive Top-K → **Citations** → Generation →
  OutputGuard.
- **Pluggable LLM providers** behind an `LLMProvider` Protocol (`services/llm_provider.py`,
  `services/llm_providers/{openai_compat,anthropic,chained,circuit_breaker,factory}.py`) — this
  **is** the "swap to Olmo 2 later" seam, already built and contract-tested.
- Resilience: `ChainedProvider` fallback, OTel tracing, slowapi rate limiting, hashed audit log,
  semantic cache — all config-flagged.
- FastAPI backend + React frontend + composition-root DI in `main.py`.

**Not airgapped** (per the user): drop the capstone's local-vLLM/Ollama-only posture. Use a
**hosted OpenAI-compatible provider** for generation now (already implemented in
`openai_compat.py`), and add an **Olmo 2** leaf later — either point `openai_compat` at an Olmo 2
endpoint or drop in `llm_providers/olmo.py`. No other stage changes. This also unblocks the
cheap Cloudflare demo (no GPU box required for the doc side).

**What's genuinely new here is the geospatial half**, not the RAG:
1. geo-mention extraction as structured output from the answer,
2. a deterministic geo-resolver against *our* PostGIS layers, and
3. map wiring (answer → highlight/zoom + EO overlay) and map-click → docs reverse lookup.

## Value gate

1. **Who needs this / what breaks without it?** Land & water managers, researchers, and the
   portfolio's credibility. The map tells you *a reach is degrading*; it can't tell you *what the
   watershed plan says about it, who has jurisdiction, or what restoration was already proposed*.
   Without a document surface the map is an island. **Passes.**
2. **Would we build it if it cost a week?** It costs far less by reusing the harness — the new
   work is the geo delta + corpus swap. It's the second half of the "explainable geospatial"
   story (Olmo 2 explains, OlmoEarth sees) and is independently demoable. **Passes.**
3. **Who owns saying no?** Joshua Dell (solo). **Named.**

## Goal

Given a corpus of public San Juan-watershed documents (PDFs + web pages), let a user:

- **Ask** a natural-language question and get an answer that **cites only the retrieved
  sources** (doc + page/section) — reusing the harness Citations stage + CRAG grounding, with a
  "no source, no claim" guarantee.
- **See the geography** an answer refers to: the answer emits structured `geo_mentions[]`
  (rivers, reservoirs, HUC IDs, towns, reaches — **free-form**), a resolver turns them into
  geometry, and the map **zooms + highlights** those areas, optionally overlaying the riparian
  extent / health / invasive layers there.
- **Click the map** anywhere and get a cited summary of the documents relevant to *that area*
  (reverse lookup) + a ranked doc list.

## Scope — three surfaces

1. **RAG Q&A with citations** (`POST /docs/ask`) — the harness pipeline, corpus-swapped, with
   `geo_mentions[]` added to the response contract.
2. **Answer → map** — resolve `geo_mentions[]` to `resolved_geometries[]`; frontend jumps +
   highlights + (optional) overlays EO layers.
3. **Map click → docs** (`POST /docs/for-area`) — resolve a clicked point/polygon to canonical
   spatial keys → retrieve geo-linked chunks → cited area summary + top docs.

Non-goals for MVP: in-UI PDF upload (curated corpus first — see Open questions), species-level
document tagging, multi-basin corpora, river-mile / "between X and Y" parsing, PDF snippet-image
highlighting (text-anchor citations first).

## Where the two systems join

The harness keeps its **Qdrant** semantic store (chunks + embeddings + reranking + CRAG) — no
migration to pgvector. The **riparian PostGIS** owns the *geospatial* half so the map-click
reverse lookup is a fast spatial join against layers we already have. The two are cross-
referenced by `chunk_id`.

New PostGIS schema (additive migration `sql/docintel_migration.sql`, **no `create_schemas.sql`
edit**):

- `docs.documents` — `id`, `title`, `authors`, `year`, `agency`, `source_url`, `doc_type`
  (`plan|report|paper|minutes|metadata|webpage`), `license`, `sha256`, `retrieved_at`.
- `docs.chunk_geo_mentions` — `id`, `chunk_id` (→ Qdrant point id), `doc_id`, `mention_text`,
  `mention_type` (`river|reservoir|huc|town|reach|place|coord|bbox`), `confidence`,
  `resolved_kind`, `resolved_ref` (e.g. `huc12=140801051001`, `nhd_reach_id=…`),
  `geom geometry(Geometry,4269)`.

Chunk text/embeddings stay in Qdrant; only the geo-links land in PostGIS. CRS **EPSG:4269**,
`geom::geography` for distance/area, GiST indexes. Medallion lane: `docs` schema is its own
bronze-like ingest; the geo-linking is the "silver" spatial step; `/for-area` rollups are "gold".
Never write upstream.

## Ingestion (reuse harness, add a geo-tagging stage)

Reuse the harness ingestion wholesale (discover → fetch/snapshot → extract w/ page numbers →
table-aware/adaptive chunk → embed → Qdrant), changing only the corpus and adding one stage:

1. **Corpus swap** — seed list of San Juan-watershed sources + shallow crawl of linked PDFs (SJRIP,
   USGS, BLM/USFS, EPA, watershed-plan hosts) + web pages as readable-text snapshots. Store the
   seed list in-repo for reproducibility; record `source_url` / `sha256` / `retrieved_at` per doc.
2. **New: geo-tag chunks** — run geo-mention extraction on each chunk at ingest time; resolve
   deterministically to spatial keys; write `docs.chunk_geo_mentions`. This is what powers the
   map-click reverse lookup (deterministic join, not an LLM call at query time).

The harness already preserves `page_start/end` + `section_path` on chunks — that's the citation
anchor; keep it.

## Retrieval + generation (reuse; extend the output contract)

- **Retrieval / CRAG / citations:** unchanged — hybrid retrieval + reranking + `document_grader`
  CRAG + the existing Citations stage + Input/Output guards. Grounding discipline ("answer only
  from provided chunks", every claim → ≥1 citation, "insufficient evidence" when weak) is already
  the harness's behavior — keep it as a gate.
- **Generation provider:** hosted OpenAI-compat now (`openai_compat.py`); **Olmo 2** later via the
  `LLMProvider` seam. The `ChainedProvider` can keep a cheap model primary + Olmo 2 as it matures.
- **New output field — `geo_mentions[]`:** extend the answer step to emit structured geo mentions
  in the *same* generation call (free-form text + type guess + confidence). The LLM proposes
  mentions; it does **not** emit coordinates/bboxes (the resolver's job — prevents hallucinated
  geometry). Response contract becomes `{ answer, citations[], geo_mentions[] }`.

## Geo resolution (free-form → geometry) — deterministic-first, our layers first

Ordered resolver (the "full free-form place resolution" the user wants, made safe by grounding it
in *our* data before any gazetteer):

1. **Internal layers** — match to HUC8/HUC12 polygons, `gold.reach_riparian` reaches,
   `bronze.nhd_flowlines` (by `gnis_name`), study-area place list.
2. **Gazetteer fallback** — GNIS / NHD names for places outside our tables (flagged
   lower-confidence, clipped to the AOI bbox).
3. **Ambiguity** — return multiple candidates with confidence; UI asks the user to pick.

Output: `resolved_geometries[]` = `{ mention_text, kind, ref, geom (GeoJSON), confidence }`.

## Map integration (riparian frontend, MapLibre)

- **Answer → map:** fit/zoom to the union of `resolved_geometries[]`, highlight each, and offer a
  toggle to overlay the riparian extent / health / invasive layers *for that area*. Citations panel
  click-links to highlighted geometries.
- **Map click → docs:** click → `/docs/for-area` → cited area summary (generated from the
  geo-linked chunks) + ranked docs + resolved spatial keys (HUC12, nearest river, nearest reach).
  Two-tier retrieval: deterministic geo-linked chunks first, semantic fallback second.
  "Insufficient evidence" state when nothing links.

The doc Q&A UI can live in the riparian React app (new panel) or reuse the harness React frontend
pointed at the same backend — decide in Phase D based on how much of the harness UI transfers.

## Hosting (cheap demo — not airgapped)

- **Frontend:** Cloudflare Pages (free) — shareable demo URL.
- **Static geodata:** PMTiles (reaches/HUCs/extent) + COGs (annual layers) on **R2**; app reads
  them directly — no always-on tile server.
- **RAG backend:** the harness FastAPI, scale-to-zero container (Cloud Run / Fly). Qdrant hosted
  (Qdrant Cloud free tier or a small always-cheap instance). Since we're not airgapped, generation
  is a **hosted API call** — no GPU box for the demo.
- **PostGIS:** the riparian DB (geo-links + spatial join). Serverless Postgres (Neon/Supabase) for
  the demo if the riparian DB isn't hosted.
- **Model:** hosted OpenAI-compat now; Olmo 2 later. Token caps + semantic cache (already in the
  harness) keep it cheap.

## Acceptance criteria (externally observable)

- `POST /docs/ask` returns `{ answer, citations[], geo_mentions[] }`; every claim is backed by a
  citation resolvable to a doc + page; "insufficient evidence" when retrieval is weak (harness CRAG
  behavior preserved).
- `geo_mentions[]` resolve to `resolved_geometries[]`; asking about a named river/reach/HUC **moves
  and highlights the map** to that geometry.
- `POST /docs/for-area` on a clicked point returns a cited area summary + ranked docs + resolved
  HUC12 / nearest river / nearest reach.
- The generator is swappable to Olmo 2 with **no change** to retrieval, citations, geo-resolution,
  or UI (the `LLMProvider` contract test still passes).
- Corpus ingestion is reproducible from the in-repo seed list.
- Runs as a public demo link without a dedicated GPU.

## Affects

- **Fork/vendor** the Re-find Catalog `production-app` as the RAG backend (submodule, subtree, or a
  trimmed copy — decide in Phase A). Keep its `services/`, `llm_providers/`, guards, and pipeline.
- **New PostGIS schema:** `sql/docintel_migration.sql` (`docs.documents`, `docs.chunk_geo_mentions`).
- **New pipeline stage:** geo-mention extraction at ingest (writes `chunk_geo_mentions`) + a
  `geo_mentions[]` field on the query response (extend `rag_pipeline.py` output + `models.py`).
- **New backend endpoints:** `POST /docs/ask` (harness pipeline + geo field), `POST /docs/for-area`.
- **New resolver module:** free-form mention → `resolved_geometries[]` against riparian PostGIS.
- **New frontend:** Q&A + citations panel, answer→map highlight, map-click→docs — in the riparian
  MapLibre app; reuse EO layers as overlay targets.
- **Olmo 2 provider:** `llm_providers/olmo.py` (or repoint `openai_compat`) — Phase F.

## Upstream dependencies (require explicit sign-off per CLAUDE.md)

- The harness's own stack (Haystack 2.0, Qdrant, FastAPI, Docling, rerankers) — inherited by
  forking, but note them since they're new to *this* repo.
- A hosted OpenAI-compatible LLM endpoint (generation) + embedding model.
- **Olmo 2** availability (open weights or a low-cost hosted endpoint) — gates the swap, not MVP.
- **Corpus:** public San Juan-watershed documents, findable + licensed for indexing (San Juan Basin
  Watershed Management Plan, SJRIP / USGS / EPA / BLM / USFS reports). **We don't have the corpus
  yet** — sourcing it is Phase A.

## Non-functional constraints

- "No source, no claim"; citation-faithfulness is a gate (the harness already enforces it — keep the
  eval).
- LLM never emits geometry; resolver is deterministic-first and AOI-clipped.
- Cheap public demo (scale-to-zero, token caps, semantic cache). No airgap requirement.
- Provenance (`source_url`, `sha256`, `retrieved_at`, page numbers) stored per chunk.

## Phased implementation

- **Phase A — vendor harness + corpus:** bring in `production-app`; assemble the watershed seed
  list; ingest ~20–50 docs into Qdrant; verify page-accurate chunks + provenance.
- **Phase B — Q&A with citations:** run the harness pipeline on the new corpus with a hosted
  provider; confirm citations + CRAG + guards + faithfulness eval on watershed questions. No map yet.
- **Phase C — geo extraction + resolver:** add `geo_mentions[]` to the response; build the
  deterministic resolver against PostGIS layers → `resolved_geometries[]`.
- **Phase D — map wiring:** answer→highlight/zoom + EO overlay in the riparian MapLibre app.
- **Phase E — reverse lookup:** geo-tag chunks at ingest (`chunk_geo_mentions`) + `POST /docs/for-area`
  + map-click UX.
- **Phase F — Olmo 2 + deploy:** Olmo 2 provider behind the seam; Cloudflare demo deploy.

## Open questions

- **Vendoring:** git submodule vs. subtree vs. trimmed in-repo copy of `production-app`? (Affects how
  upstream fixes flow back.)
- **Corpus intake:** curated seed corpus only (MVP default), or in-UI PDF upload too (deferred)?
- **Hosted model (pre-Olmo2):** lowest-cost vs. slightly-higher-quality-still-cheap for the demo?
- **Frontend:** extend the riparian React app, or reuse the harness React UI against the same backend?

## Significance check

**ADR: yes** — introduces a forked RAG subsystem, a new `docs` PostGIS schema, a Qdrant dependency,
a geospatial resolver, and an Ai2-model integration path. Draft
`docs/decisions/2026-07-04-document-intelligence-subsystem.md` before Phase B (record: reuse Re-find
Catalog harness; Qdrant for semantic + PostGIS for geo; not airgapped → hosted providers; Olmo 2 via
the existing `LLMProvider` seam).

## Closing the loop

> **This spec captures the handoff.** Once Phase C ships, what did the geo half actually require
> (structured `geo_mentions[]`, the LLM-never-emits-geometry rule, deterministic-resolver-first)?
> Encode the durable lessons across the 5 surfaces — the harness gave us the RAG; the geospatial
> grounding is the part this project invents.
