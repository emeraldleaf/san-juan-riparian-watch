# docintel — Document Intelligence subsystem

RAG Q&A with citations over San Juan watershed documents, **map-linked** to the riparian
platform. Built by **reusing the Re-find Catalog RAG harness** (Haystack 2.0 + Qdrant + a
10-stage pipeline with CRAG + citations + guards + pluggable LLM providers) and adding the
**geospatial delta** this project invents. See the
[spec](../docs/specs/2026-07-04-document-intelligence-rag.md) and
[ADR](../docs/decisions/2026-07-04-document-intelligence-subsystem.md).

```
docintel/
├── corpus/                 # seed_sources.yaml — reproducible watershed document list
├── backend/                # VENDORED (trimmed) Re-find Catalog RAG backend (see manifest)
├── geo/                    # NEW — the geospatial half (mentions + resolver)
│   ├── models.py           #   GeoMention / ResolvedGeometry schemas + MentionType
│   └── resolver.py         #   deterministic free-form-place -> geometry against PostGIS
└── scripts/
    └── vendor_harness.sh   # copies the trimmed harness from the capstone repo
```

## What is reused vs. new

| Reused from the harness (vendored, do not re-derive) | New here (this project's IP) |
|------------------------------------------------------|------------------------------|
| Haystack ingestion, table-aware/adaptive chunking, PyPDF2+Docling extraction | Corpus swap → watershed docs (`corpus/seed_sources.yaml`) |
| Qdrant hybrid retrieval + reranking | Geo-mention extraction as structured output (`geo_mentions[]`) |
| 10-stage pipeline: guards → cache → router → retrieval → **CRAG** → **citations** → gen | Deterministic **geo-resolver** vs. PostGIS (`geo/resolver.py`) |
| `LLMProvider` Protocol + providers (openai_compat/anthropic/chained) | `POST /docs/for-area` map-click reverse lookup |
| Resilience: OTel, rate limiting, hashed audit, semantic cache | `docs` PostGIS schema (`sql/docintel_migration.sql`) |
| Citation-faithfulness eval harness | Map wiring (answer → highlight/zoom + EO overlay) in the riparian frontend |

## Vendoring

The backend under `backend/` is a **trimmed in-repo copy** of
`my-capstone-rag/production-app/app/backend` (ADR: copy over submodule/subtree — simplest to run
+ deploy; upstream is stable). Run:

```bash
bash docintel/scripts/vendor_harness.sh            # uses the default capstone path
CAPSTONE=/path/to/my-capstone-rag bash docintel/scripts/vendor_harness.sh
```

The script copies `services/`, `llm_providers/`, `middleware/`, `observability/`, `prompts/`,
`main.py`, `config.py`, `models.py`, `auth.py` and **omits** the legal/financial corpus, weekly
snapshots, VM/airgap scripts, evals, and course-submission tooling. After vendoring:

1. **Re-domain the prompts** in `backend/prompts/` from legal/financial → watershed science
   (the retrieval/CRAG/citation *logic* is domain-agnostic; only the prompt text changes).
2. **Not airgapped** → set the generation provider to a hosted OpenAI-compatible endpoint in
   `backend/config.py` / `.env`. Olmo 2 later = one leaf behind the `LLMProvider` Protocol
   (repoint `openai_compat` or add `llm_providers/olmo.py`) — no other change.
3. **Wire the geo delta:** add `geo_mentions[]` to the pipeline's response model, call
   `geo/resolver.py` to produce `resolved_geometries[]`, and add the `/docs/ask` + `/docs/for-area`
   routes.

## How it plugs into the platform

- **Aspire:** `docintel/backend` is a new Python service in the graph (alongside `python-etl`),
  sharing the PostGIS connection. Qdrant is a new container/hosted dependency.
- **PostGIS:** apply `sql/docintel_migration.sql` (adds the `docs` schema). Chunk text/embeddings
  live in **Qdrant**; only geo-links live in PostGIS, joined to Qdrant by `chunk_id`.
- **Frontend:** the riparian MapLibre app gains a Q&A + citations panel; answers highlight/zoom the
  map and can overlay the EO layers for the mentioned area.

## Status

Phase A scaffolding. `backend/` is populated by `vendor_harness.sh` (not committed until vendored
+ re-domained). `geo/` holds the new-IP scaffolds with live-query TODOs. See the spec's phased
plan (A vendor+corpus → F Olmo 2 + Cloudflare deploy).
