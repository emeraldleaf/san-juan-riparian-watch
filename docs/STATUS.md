# Project Status

**Last updated:** 2026-07-07

Cross-session entry point. Surfaced automatically at session start by the
`inject-status.sh` hook. Refresh with `/sync-status`.

## Where we are

Portfolio piece for the Ai2 "AI for the Planet" Senior SWE role — **san-juan-riparian-watch**
(public). All work merged to `main` (PR #2, CodeRabbit-reviewed). Three tracks + the app run
end-to-end locally.

### Working now (verified end-to-end)
- **Delineation (Stage 1):** RF baseline → **NMRipMap-trained** on the 2 NM tiles (spatial-CV F1
  0.90–0.92, vs weak-label 0.00–0.71); HAND envelope; MMU+simplify in `_vectorize`. On the map +
  NMRipMap reference overlay toggle.
- **Doc-intelligence (Track 3):** RAG (Qdrant + CRAG + citations, local Ollama) → geo-resolver
  (rivers/reaches/HUCs) → `/docs/ask` → frontend Q&A panel that highlights answers on the map.
  Harness is PRIVATE (`riparian-rag-harness`); public repo holds the geo delta + API contract.
- **Perf:** index-backed bbox pre-filter on all MVT tile queries (10–40× faster); extent de-noised.

### Runtime (local) — how to bring it up
- **Stable DB** (off the flaky external-drive Docker): `docker run -d --name riparian-pg-stable
  -p 55432:5432 -v ~/riparian-pgdata-stable:/var/lib/postgresql/data postgis/postgis:16-3.4`
  (trust auth, max_connections=200).
- **C# API** (Release): `ConnectionStrings__ripariandb="Host=localhost;Port=55432;Database=ripariandb;Username=postgres;Maximum Pool Size=40"
  ASPNETCORE_URLS=http://localhost:5237 dotnet run -c Release --project RiparianPoc.Api`.
- **docintel** (in riparian-rag-harness): `RIPARIAN_DB_URL=postgresql+psycopg2://postgres@localhost:55432/ripariandb
  LLM_MODEL=llama3.2:3b uv run uvicorn docintel_server:app --port 8100` + Qdrant :6333 + Ollama.
- **Frontend:** `cd frontend && npm run dev` → http://localhost:3000.

### Roadmap (priority)
1. **Shareable** — deploy a demo link (Cloudflare per docintel spec) or a demo video + write-up.
   Right now it only runs on the local machine → a reviewer can't see it (the #1 practical gap).
2. **OlmoEarth flagship** — embeddings + light head + RF-vs-OlmoEarth disagreement map (the Ai2
   differentiator). `delineation/olmoearth.py` scaffold exists; needs the token-mask fix + a GPU
   for the real run (Nano/CPU for one small tile).
3. **Invasives + change** — tamarisk/Russian-olive cover within the extent (`health/invasive.py`)
   → spread over time (Stage-3 spec). Manager-relevant, on-thesis.
4. **Empty views** — NDVI Health / SMP Score / Vegetation are empty (0 rows); need the NDVI/health
   ETL (heavy; back up first — buffers truncation cascades).
5. **MVT for extent + NMRipMap** — the last GeoJSON layers; the fully-correct serving path.

### Original framing (retained below)
Renamed → **san-juan-riparian-watch**. README rewritten to the delineation/health/change framing.
Three tracks.

### Track 1 — Encoding-loop method port (DONE, verified)
All three loops from the NextAurora repo are ported and dogfooded: 5 surfaces × 3 tiers,
lean CLAUDE.md (333 lines), `.coderabbit.yaml`, `architecture-reviewer` agent, 6 commands +
10 skills, CI gates (lean-canon + doc/diagram pairing, both green), and the diagrams loop
(seed diagram renders SVG+PNG). See CONTEXT.md.

### Track 2 — Riparian delineation (baseline slice VERIFIED end-to-end)
Reframed off fixed hydrology buffers to a learned pipeline. **The baseline vertical slice
runs end-to-end against the live DB:** STAC datacube → 22 multitemporal features → weak
labels (ESA WorldCover ∧ io-lulc "woody-near-water" ∧ NWI) → RandomForest → **spatial**
cross-validation → vectorize → `silver.riparian_extent`. Served via `GET /api/riparian/extent`.
First real run: 102k weak-labeled samples, spatial-CV ROC-AUC 0.90 / precision 0.81, 66
riparian polygons written.

**Accuracy lever #4 landed (2026-07-06): train the RF on NMRipMap truth, not weak labels.**
`run_delineation(label_source='nmripmap')` rasterizes NMRipMap mapped-riparian polygons into
per-pixel training truth (writes `model_version='rf-nmripmap-v1'`). Result on the 2 NM tiles
(5-fold spatial-CV): **Malpais F1 0.71→0.895 (ROC-AUC 0.96); Animas ~0.00→0.924 (ROC-AUC 0.98)** —
the weak-label model had ~zero agreement with real riparian on the ag-valley tile. Map (method=rf)
now serves NMRipMap-trained extent for Animas + Malpais; Turkey Creek (CO) stays weak (no NMRipMap
— needs CO-RIP). Honest caveat: full-tile map partly reproduces its own tile's NMRipMap; the
spatial-CV number is the generalization metric that matters. Next: CO-RIP for CO, OlmoEarth flagship.

### Track 3 — Document Intelligence (RAG + map-linked geo citations) — SPEC + Phase-A scaffold
New second surface over the same AOI: Olmo 2 *explains* (RAG Q&A with citations over watershed
docs), OlmoEarth *sees* (EO layers), joined at the map. **Decision: reuse the existing
Re-find Catalog RAG harness** (`the private Quartzose repo` — Haystack 2.0 +
Qdrant + 10-stage pipeline w/ CRAG + citations + guards + pluggable `LLMProvider`); build only the
**geospatial delta** + corpus swap. **Not airgapped** → hosted OpenAI-compat provider now, Olmo 2
later behind the existing provider seam. Landed this session:
- Spec `docs/specs/2026-07-04-document-intelligence-rag.md` + ADR
  `docs/decisions/2026-07-04-document-intelligence-subsystem.md` (vendoring=trimmed copy;
  Qdrant semantic / PostGIS geo split, joined by chunk_id; LLM-never-emits-geometry invariant).
- `sql/docintel_migration.sql` — additive `docs` schema (`documents`, `chunk_geo_mentions`).
- `docintel/` scaffold: `corpus/seed_sources.yaml` (11 real public San Juan docs incl. SJRIP
  Bassett-2015 riparian/invasive + monitoring reports), `scripts/vendor_harness.sh` (trimmed
  harness copy), and the NEW-IP geo modules `geo/models.py` + `geo/resolver.py`.

**Phase A + B BUILT & VERIFIED end-to-end (2026-07-05).** Public/private split held:
- **Private repo `github.com/emeraldleaf/riparian-rag-harness`** (harness must not be public):
  vendored the RAG harness, ingested 7 watershed PDFs → **Qdrant `riparian_watershed` (527 pts)**,
  re-domained prompts (generation + CRAG + system), and a **live cited answer** verified via local
  Ollama (`llama3.2:3b`) — no hosted key needed. `scripts/ask_map_linked.py` +
  **`docintel_server.py` (FastAPI `POST /docs/ask`)** return `{answer, citations, geo_mentions,
  resolved_geometries}`; verified over HTTP.
- **Public repo**: `sql/docintel_migration.sql` **applied** (`docs` schema live); resolver PostGIS
  queries **implemented + verified** ('Animas River near Farmington' → reach geom, HUC8/HUC12 codes
  resolve, towns honestly unresolved). `docintel/API_CONTRACT.md` added. All on PR #2.
- **Full loop demonstrated:** question → cited answer → geo_mentions → resolved reach geometries.
- **FULL STACK working end-to-end (2026-07-06):** frontend `DocIntelPanel` (App.tsx) → docintel
  `POST /docs/ask` → cited answer + `resolved_geometries` highlighted on the MapLibre map (amber
  line+fill, auto-fit). tsc+vite build clean; CORS 200 from :3000. Citations now structured (from
  retrieved docs, not answer regex). Verified /docs/ask: `geo_available:true`, 4 real source PDFs,
  San Juan + Animas rivers → reach MultiLineStrings.
- **DB stability SOLVED (root cause + fix):** Docker Desktop's containerd store on the **external
  drive** fails R/W I/O (`meta.db`/blob `input/output error`) → Postgres zombies, new containers
  won't start. Durable fix = move Docker's disk-image location off the external drive (GUI). **Stable
  workaround in place:** a standalone internal-disk PostGIS —
  `docker run -d --name riparian-pg-stable -p 55432:5432 -v ~/riparian-pgdata-stable:/var/lib/postgresql/data postgis/postgis:16-3.4`
  (trust auth; `~/riparian-pgdata-stable` = a copy of pgdata). Point docintel at it via
  `RIPARIAN_DB_URL=postgresql+psycopg2://postgres@localhost:55432/ripariandb`.
- **Run the demo:** stable PG (above) + Qdrant (:6333) + Ollama + `LLM_MODEL=llama3.2:3b uv run
  uvicorn docintel_server:app --port 8100` (in riparian-rag-harness) + `cd frontend && npm run dev`.
- **Optional next:** `/docs/for-area` reverse lookup + ingest-time `docs.chunk_geo_mentions` tagging
  + hosted/Olmo 2 provider swap. In-browser click-through is the user's final visual check.

## Recently landed
- README.md rewritten accurate/current (delineation/health/change; riparian/ package; MapLibre;
  tests+CI; honest stratified results). Doc-intelligence spec+ADR+scaffold (Track 3 above).
- Baseline delineation modules: `stac_datacube.py`, `feature_builder.py`,
  `weak_label_sampler.py` (STAC land-cover — replaced dead NLCD/LANDFIRE ArcGIS endpoints),
  `delineation_baseline.py`, `delineation_validate.py`, `delineation_runner.py`.
- `sql/delineation_migration.sql` applied; `/api/riparian/extent` endpoint.
- Strategic AOI pivot encoded in the Stage-1 spec (revision 2026-07-03b).

## AOI decision (San Juan River HUC watershed, CO + NM)
- Organizing unit = **HUC12** (713 in subregion 1408), subset-first then scale.
- **Three representative tiles locked** (verified against USGS WBD):
  - Headwaters CO — **140801010401** Turkey Creek — bbox (-107.035, 37.348, -106.915, 37.49)
  - Mid-valley NM — **140801041003** Tucker Canyon–Animas River — bbox (-108.017, 36.872, -107.804, 36.977)
  - Lowland/ag — **140801051001** Malpais Arroyo–San Juan River — bbox (-108.822, 36.81, -108.673, 36.951)

## What's next (network-first build, on the 3 tiles first)
1. **HUC12 tiling** — add `huc12` column to `silver.riparian_extent` + samples; runner writes
   per-tile (restartable); run all 3 tiles.
2. **Stage 1A — HAND / valley-bottom envelope** from 3DEP DEM (needs `pysheds`/`richdem` — a
   new dep, requires sign-off) to constrain inference + cut false positives.
3. **Per-reach outputs** — NHD flowlines → 250 m reaches → `%riparian_cover` + confidence +
   quality flags.
4. **Reference-layer validation** — NMRipMap (NM) + CO-RIP (CO), IoU/F1 stratified by stream
   order; validate NM vs CO separately.
5. **OlmoEarth-everywhere** on the **Hyperstack GPU VM** — embedding store, head training,
   baseline-vs-OlmoEarth disagreement maps.
6. **Web app** — frontend map layer for extent (endpoint exists) + reach summaries.

## Environment notes
- ETL host env is polluted (pandas bumped to 3.0.3 by odc-stac; a broken `vision` nspkg
  warning is cosmetic). The real ETL runs in Docker; new delineation deps installed on host
  for verification. Consider a dedicated venv.
- Dead upstream endpoints: repo's `NLCD_EROS_URL` (HTML) + LANDFIRE `US_250EVT` (404) — the
  delineation labels no longer use them (STAC land-cover instead); the *existing* NLCD/LANDFIRE
  ETL steps may need the same repointing.
