# ADR: Document-intelligence subsystem — reuse the Re-find Catalog RAG harness

**Date:** 2026-07-04
**Status:** Accepted
**Owner:** Joshua Dell (solo)
**Related:** [Doc-intelligence spec](../specs/2026-07-04-document-intelligence-rag.md)

## Context

We are adding a second surface over the San Juan AOI: a document-intelligence layer (RAG Q&A
with citations over published watershed documents) that links its answers to geography on the
existing riparian map. The obvious risk is re-implementing a production RAG stack — retrieval,
reranking, CRAG, citations, guards, provider fallback, evals — from scratch.

We already own a production-grade RAG system: **Re-find Catalog**
(`/Users/joshuadell/Dev/AI Course/my-capstone-rag/production-app`) — Haystack 2.0 + Qdrant, a
10-stage pipeline (InputGuard → Memory → Cache → Router → Retrieval → CRAG → Adaptive Top-K →
Citations → Generation → OutputGuard), pluggable LLM providers behind an `LLMProvider` Protocol,
resilience (ChainedProvider fallback, OTel, rate limiting, hashed audit), FastAPI + React, and a
citation-faithfulness eval harness.

The user directed: **use it as the harness, and it does not need to be airgapped.**

## Decision

**Reuse the Re-find Catalog harness; build only the geospatial delta + corpus swap.**

1. **Keep the harness in a separate PRIVATE repo** (revised 2026-07-04b — the harness is coursework
   and must not be published). The private repo vendors a trimmed copy of the backend (keep
   `services/`, `llm_providers/`, `middleware/`, `observability/`, `prompts/`, `main.py`,
   `config.py`, `models.py`, `auth.py`; drop the legal/financial corpus, snapshots, VM/airgap +
   submission tooling) via its own `vendor_harness.sh`. **This public repo holds only the
   geospatial delta + the seam contract** — `docintel/geo/` (resolver IP), `corpus/seed_sources.yaml`,
   `docintel/API_CONTRACT.md`, `sql/docintel_migration.sql`, and the frontend integration. The
   private backend **imports the public `docintel/geo/` resolver** and reads the public corpus list;
   dependency flows private → public only, so nothing private leaks into the portfolio repo.
   *(Superseded: the original "trimmed in-repo copy into docintel/backend" — that would have
   published the harness.)*

2. **Two datastores, split by concern.** Qdrant remains the **semantic store** (chunks,
   embeddings, hybrid retrieval, reranking, CRAG) — no migration to pgvector. The riparian
   **PostGIS** owns the **geospatial** half (new additive `docs` schema:
   `docs.documents`, `docs.chunk_geo_mentions`) so the map-click reverse lookup is a fast spatial
   join against layers we already have (`bronze.nhd_flowlines`, `gold.reach_riparian`, HUC12).
   The two are cross-referenced by `chunk_id`.

3. **Not airgapped → hosted providers.** Drop the capstone's local-vLLM/Ollama-only posture. Use a
   hosted OpenAI-compatible provider for generation now (already implemented in
   `llm_providers/openai_compat.py`); this removes the GPU requirement for the demo. **Olmo 2**
   arrives later as another leaf behind the existing `LLMProvider` Protocol — either repoint
   `openai_compat` at an Olmo 2 endpoint or add `llm_providers/olmo.py`. No other stage changes.

4. **The genuinely new work is geospatial**, and it lives here (not in the harness): (a) a
   `geo_mentions[]` field emitted by the generation step, (b) a **deterministic geo-resolver**
   (our PostGIS layers first, gazetteer fallback AOI-clipped, ambiguity → user picks), and (c) map
   wiring (answer → highlight/zoom + EO overlay) and `POST /docs/for-area` reverse lookup.

## Alternatives considered

- **Build a fresh Python FastAPI + pgvector RAG service.** Rejected — re-derives citations, CRAG,
  guards, provider fallback, and evals we already have working and eval'd.
- **Pure Cloudflare-native (Workers + prebuilt indexes in R2, no Postgres/Qdrant).** Rejected as
  primary — cheapest to host but splits the data model away from PostGIS + the EO layers and
  discards the harness. Retained as a fallback if hosted Qdrant/Postgres tiers prove insufficient.
- **Migrate the harness from Qdrant to pgvector to unify on PostGIS.** Rejected — a full re-index
  for no functional gain; the clean split (Qdrant semantic / PostGIS geo, joined by `chunk_id`) is
  simpler and keeps the harness intact.
- **Keep the local-model airgap posture.** Rejected per the user — hosted providers are cheaper to
  demo and the `LLMProvider` seam makes the eventual Olmo 2 swap a one-file change anyway.

## Consequences

- **Unlocks** the "explainable geospatial" story cheaply: Olmo 2 explains (documents, cited),
  OlmoEarth sees (EO layers), joined at the map. Independently demoable.
- **Costs / new to this repo:** a Qdrant dependency, the harness stack (Haystack, Docling,
  rerankers), a hosted-LLM + embedding endpoint, and a `docs` schema — all flagged for sign-off in
  the spec. The vendored copy must be kept lean (no legal-domain prompts/corpus) and its prompts
  re-domained to watershed science.
- **Boundaries:** the C# API stays the geo/GeoJSON surface; `docintel/` is a separate Python
  service in the Aspire graph; they share PostGIS and the MapLibre frontend. Medallion one-way
  flow holds — `docs` is its own ingest lane; geo-linking is the spatial step; `/for-area` rollups
  are gold; never write upstream.
- **Guarantees kept from the harness:** "no source, no claim" citation faithfulness (with its
  eval), CRAG grounding, input/output guards. New invariant added here: **the LLM never emits
  geometry** — it proposes free-form `geo_mentions[]`; the deterministic resolver produces shapes.
- **Revisit** if the corpus grows past a single basin, if in-UI upload is added, or if a
  fully-local/airgapped deployment is later required.
