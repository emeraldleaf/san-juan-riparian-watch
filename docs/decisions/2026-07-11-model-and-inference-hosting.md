# ADR: Model artifacts on HuggingFace, batch inference on-demand, map demo static

**Date:** 2026-07-11 · **Status:** Accepted (planning) · **Supersedes:** nothing

## Context

Three hosting questions keep getting conflated. They are separate concerns with different
answers, and merging them is how projects end up paying for an idle GPU:

1. **Model artifact distribution** — where do the weights live?
2. **Inference runtime** — where does the model *run*?
3. **The public demo** — how does a reviewer see the map without logging in?

Constraints that actually bind us:
- Riparian monitoring is **annual/seasonal batch**, not interactive. Nobody needs a sub-second
  riparian prediction.
- The doc-intelligence backend (**Quartzose**) is **private and must not be published**, so it
  cannot be part of any public demo regardless of hosting.
- This is a portfolio piece: a reviewer must be able to click a link and see something, with no
  account, no cold start, and no bill if it goes viral.
- The project already lives on a **flaky external drive**; anything that depends on local Docker
  staying healthy is not a deployment story.

We also have a working precedent to copy: Ai2 ships OlmoEarth as **weights on HuggingFace + code
on GitHub + you run the pipeline yourself.** They do **not** operate a public prediction API.

## Decision

**Split the three concerns; pick the cheapest correct tool for each.**

### 1. Model artifacts → **HuggingFace Hub**
```
huggingface.co/<user>/OlmoEarth-FT-SanJuan-Riparian
  model.ckpt · config.yaml · README.md (+ label_crosswalk.csv, annotation_features.geojson)
```
Mirrors Ai2's own distribution pattern. Free, versioned, citable, and it is where EO people
already look.

### 2. Inference → **on-demand batch (Modal / RunPod serverless)**, explicitly **not** an always-on GPU
```
POST job {aoi, year} → pull S2 → 12 monthly mosaics → tile inference → write COG → return URL
```
Outputs (COG / GeoJSON) to cheap object storage (Cloudflare R2 / B2 / S3). Idle cost ≈ **$0**.

### 3. Public map demo → **static, no backend at all**
Export the PostGIS layers to **PMTiles** (single-file tile archive, read by MapLibre over HTTP
range requests) and serve the React build + `.pmtiles` from **GitHub Pages / Cloudflare Pages**.
**No API, no database, no cold start, $0.** The engineering-review page already ships this way.

## Consequences

**Good**
- **Zero idle cost.** The expensive thing (GPU) only exists while a job runs; the always-available
  thing (the map) is static files.
- The demo **cannot go down** and cannot be broken by the external drive, Docker, or a dead DB.
- Artifact hosting is decoupled from serving: the weights are useful to others even if we never
  run an endpoint.

**Bad / accepted**
- The static map is a **snapshot**, not live — no date-parameterised tiles unless baked in, and no
  doc-intelligence Q&A (which is private anyway, so no loss).
- Batch inference has **latency in minutes**, not milliseconds. Acceptable: annual monitoring.
- Two deploy paths to maintain (static demo + batch job) instead of one app.
- Modal/RunPod is a **vendor dependency**; mitigated because the job is a plain container and the
  weights are on HF — portable by construction.

## Alternatives rejected

| Option | Why rejected |
|---|---|
| **Always-on GPU endpoint** (SageMaker / Vertex / HF Inference Endpoints) | Pays 24/7 for a workload that runs a few times a year. Premature; revisit only if real usage appears. |
| **Keep the live C# API + PostGIS as the public demo** | Requires an always-on DB + API. Cheapest credible options (Neon/Supabase free tiers) cap ~0.5 GB — our `pgdata` is ~1.6 GB (72k NWI wetlands dominate). Also a cold-start/uptime liability for a portfolio link. Keep it as the **local dev** story, which it already is. |
| **Azure (we already have `azure.yaml`/`azd`)** | Zero rework, but Postgres Flexible Server floors around **$12–15/mo** for something a reviewer looks at for 90 seconds. |
| **Oracle Cloud Always Free VM** (4 ARM cores / 24 GB, $0) | Genuinely viable and cheaper than Azure — kept as the fallback **if** a live API is later required. Rejected as the default only because the static demo needs no server at all. |
| **Publish the docintel/RAG backend** | Not an option. Quartzose is private. |

## Cost path (deliberately staged)

| Phase | What | Cost |
|---|---|---|
| 1 | Local / Colab prototype on one AOI | ~$0 |
| 2 | Static PMTiles demo on Pages | **$0** |
| 3 | Batch inference on Modal/RunPod, outputs to R2 | pay-per-job only |
| 4 | Managed endpoint | only if usage justifies it — likely never |

## References

- Ai2 OlmoEarth distribution pattern — weights on HF, code on GitHub, run-it-yourself:
  https://huggingface.co/collections/allenai/olmoearth · https://github.com/allenai/olmoearth_projects
- PMTiles (single-file tiles, MapLibre native): https://protomaps.com/docs/pmtiles
- Spec: `docs/specs/2026-07-11-stage2-invasives-tamarix.md`
