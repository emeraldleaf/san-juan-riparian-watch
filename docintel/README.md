# docintel — Document Intelligence (public geospatial half)

RAG Q&A with citations over San Juan watershed documents, **map-linked** to the riparian
platform. Built by reusing a private RAG harness (the "Re-find Catalog" system — Haystack 2.0 +
Qdrant + a 10-stage pipeline with CRAG + citations + guards + pluggable LLM providers) and adding
the **geospatial delta** this project invents. See the
[spec](../docs/specs/2026-07-04-document-intelligence-rag.md) and
[ADR](../docs/decisions/2026-07-04-document-intelligence-subsystem.md).

## Public / private split

The RAG **harness is private and stays out of this repo.** This public repo holds only
the parts that are this project's original IP — the geospatial delta and the seam contract. The
private backend depends on the public repo, never the reverse.

| **This repo (public)** | **Private RAG repo** |
|------------------------|----------------------|
| `geo/` — deterministic free-form-place → geometry resolver (the IP) | Haystack ingestion / Qdrant retrieval / rerank / CRAG |
| `corpus/seed_sources.yaml` — reproducible watershed doc list | 10-stage pipeline + input/output guards |
| `API_CONTRACT.md` — `/docs/ask` + `/docs/for-area` request/response | pluggable `LLMProvider` (hosted now, Olmo 2 later) |
| `sql/docintel_migration.sql` — `docs` schema (geo links) | re-domained watershed prompts + ingest wiring |
| frontend Q&A + map-highlight integration (riparian app) | `imports the public geo resolver as a package` |

```
docintel/
├── corpus/            # seed_sources.yaml — reproducible watershed document list
├── geo/               # NEW IP — the geospatial half
│   ├── models.py      #   GeoMention / ResolvedGeometry schemas
│   └── resolver.py    #   deterministic free-form-place -> geometry vs PostGIS
└── API_CONTRACT.md    # the public seam: /docs/ask, /docs/for-area
```

> There is **no `backend/` here.** The vendored harness lives in the private repo (which runs
> `vendor_harness.sh` there). If you clone this repo you get the resolver, the corpus list, the
> schema, and the contract — enough to see the seam, not the private harness.

## What is reused vs. new

| Reused from the private harness (not in this repo) | New here (this project's IP) |
|----------------------------------------------------|------------------------------|
| Haystack ingestion, chunking, extraction | Corpus swap → watershed docs (`corpus/seed_sources.yaml`) |
| Qdrant hybrid retrieval + reranking | Geo-mention extraction as structured output |
| 10-stage pipeline: guards → cache → router → retrieval → CRAG → citations → gen | Deterministic **geo-resolver** vs PostGIS (`geo/resolver.py`) |
| `LLMProvider` seam (hosted now, Olmo 2 later) | `docs` schema (`sql/docintel_migration.sql`) + `/docs/for-area` |

## How it plugs into the platform

- **Private backend service** owns ingestion + the RAG pipeline; it imports `docintel/geo/` from
  this repo (installed as a package / path dependency) and reads `corpus/seed_sources.yaml`.
- **PostGIS:** apply `sql/docintel_migration.sql` (adds the `docs` schema). Chunk text/embeddings
  live in **Qdrant** (private side); only geo-links live in PostGIS, joined by `chunk_id`.
- **Frontend:** the riparian MapLibre app gains a Q&A + citations panel that calls the backend via
  the `API_CONTRACT.md` shapes; answers highlight/zoom the map and overlay EO layers.
- **Not airgapped** → hosted OpenAI-compatible provider now; Olmo 2 later, one leaf behind the
  private `LLMProvider` seam — no change to anything in this repo.

## Status

Phase A scaffolding. `geo/` holds the new-IP resolver (compile-clean; live PostGIS queries are
Phase-C TODOs). Backend vendoring + ingestion happen in the private repo. See the spec's phased
plan (A vendor+corpus → F Olmo 2 + Cloudflare deploy).
