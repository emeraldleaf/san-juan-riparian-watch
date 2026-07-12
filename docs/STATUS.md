# Project Status

**Last updated:** 2026-07-11

Cross-session entry point. Surfaced automatically at session start by the
`inject-status.sh` hook. Refresh with `/sync-status`.

## Current state — git, PRs, and WHY things are where they are (2026-07-11)

**READ THIS FIRST if you are a coding agent picking up the repo.** This section explains an
intentionally unusual git state so you don't "helpfully" re-commit things or close issues early.

### Branches
- Working branch **`feat/docintel-private-split`** @ `3b824f0` (pushed to origin).
  - `ad89b67` — ETL enrichment/scoring WIP **+ review-driven bug fixes** (see below).
  - `3b824f0` — untracked build artifacts (`.sonarqube/`, `__pycache__`, `.DS_Store` now gitignored).
- **This branch is BEHIND `main`.** `main` has PRs #3 and #4 merged; this branch predates them.
  That is WHY ~10 files show as "uncommitted" here but must **NOT** be committed on this branch:
  `RiparianPoc.Api/Services/{GeoDataServices,MvtTileSql}.cs`, the C# tests, `RiparianPoc.Api.csproj`,
  `frontend/src/{App.tsx,components/NDVILayer.tsx}`, `docs/{engineering-review.html,index.html,.nojekyll}`
  are the **content of PRs #3/#4/#5**. Committing them here duplicates the PRs and will conflict.
  They reconcile when this branch is synced with `main` (rebase/merge) after PR #5 lands.
- Genuinely uncommitted + left alone: 5 misc config files (`.vscode`, `.claude/settings.json`,
  `aspire.config.json`, `README_SONAR.md`, deleted `.codacy/codacy.yaml`) — user's call.

### PRs (base = `main`)
- **#3 MERGED** — GitHub Pages: `docs/engineering-review.html` walkthrough (live at
  `https://emeraldleaf.github.io/san-juan-riparian-watch/engineering-review.html`) + root redirect.
- **#4 MERGED** — MVT tile SQL unified into `MvtTileSql.Build` + `RenderTileAsync`; C# xUnit tests
  (`RiparianPoc.Api.Tests`); `result.byte_count` span tag; stale-test-doc fixes.
- **#5 OPEN** — map-UI fixes (DEBUG colors removed, 3-way legend, stale-response guard, heatmap
  weight clamp, default recenter) + soil/wetland tile popup enrichment + `MvtTileSql` layer-name
  validation + NDVI legend/CLAUDE.md threshold reconciliation. Labeled `coderabbit`.

### Open issues (base = `main`)
- **#6 / #7 / #8** — the 3 HIGH ETL bugs from the ultracode review. Their FIXES are committed on
  `feat/docintel-private-split` (`ad89b67`) but **NOT on `main`**, so the issues stay OPEN until this
  branch's ETL work merges. Do not close them against `main` yet.

### Ultracode review (2026-07-11) — 25 confirmed (3 high / ~11 med / ~11 low), 6 refuted
All 3 HIGH + the load-bearing MEDIUM ETL/scorer bugs are fixed in `ad89b67`: buffer_wetlands rebuilt
on full run (was wiped by CASCADE); ArcGIS HTTP-200 error bodies now raise + paginator stops at first
gap (no gapped bronze); LANDFIRE EVH `32767` fill filtered from continuous stats; NLCD wired via EROS
ImageServer + GeoServer WMS fallback in `main()`; `health_scorer` aligned height/lifeform pairs +
continuous NDVI curve + **per-watershed** summary aggregation; LiDAR CHM resamples DTM onto the DSM
grid before differencing. Verified: `py_compile`, 32 pytest, live per-watershed SQL.

### Positioning — what is actually novel here (2026-07-11, READ THIS)
Two of our components **substantially reproduce published work**. Say so; do not claim otherwise.
- **Riparian extent mapping is already solved basin-wide.** CO-RIP (Woodward et al. 2018,
  ISPRS IJGI) mapped riparian corridor + vegetation for the *entire Colorado River Basin —
  including the San Juan* — using **valley-bottom delineation + Random Forest on Landsat**,
  median **κ 0.80**. Our HAND envelope ≈ their valley bottom; our RF-on-spectral ≈ their RF.
  **"We built an RF riparian classifier" is not a contribution.** Use CO-RIP as a *baseline to
  beat and a label source*, not something to re-derive.
- **Tamarisk detection is established** (S2+RF **87.8% OA**; Landsat 80–91%), and the literature
  is explicit that **phenology — specifically late-season senescence — is the discriminator**
  (Tamarix stays green after natives brown). This *indicts our OlmoEarth harness*: it mean-pools
  tokens over time, destroying exactly that signal (#9).
- **The real gap:** CO-RIP gives extent-without-species; CSU/NREL's 2018 dataset gives **3,000+
  tamarisk/Russian-olive occurrence points** but no map — CSU call them *"complementary products
  rather than a single integrated map of invasive versus native species."* **Nobody has produced
  a wall-to-wall, time-series, native-vs-invasive cover + change product at reach scale.** That,
  plus mining weak labels from existing authoritative GIS and an EO-foundation-model fine-tune,
  is the contribution. See `docs/specs/2026-07-11-stage2-invasives-tamarix.md`.
- Free ground truth found: NMRipMap `L2 = IC` ("Lowland **Introduced** Riparian Woodland and
  Scrub") = **332 tamarisk/Russian-olive polygons on the Animas alone** — but it *conflates* the
  two species; the CSU points can split them.

### NDVI health thresholds (CANONICAL)
`classify_health()` in `ndvi_processor.py` is the single source of truth:
**healthy >0.25 / degraded 0.10–0.25 / bare <0.10** (peak-growing median ~0.17). Frontend legend +
CLAUDE.md now match — do not reintroduce the old >0.3 / 0.15 values.

### "Empty views" — the 3 buffer view-mode buttons (NDVI / SMP / Vegetation)
`silver.vegetation_health`, `gold.buffer_health_score`, `silver.buffer_vegetation_structure` are all
**0 rows** in the current DB snapshot, so all three buttons render the buffer polygons in a uniform
"no-data" color (geometry draws; the *differentiating* color does not). Populating them needs the
NDVI/health/scoring ETL run — deferred until the (now-fixed) ETL bugs are validated end-to-end. Do
NOT run the ETL just to fill these before the fixes are confirmed, or you bake wrong data into the demo.

### Local runtime / DB (external-drive hazard)
- Live render verified via the **internal-disk stable PG** (data on `~/riparian-pgdata-stable`, OFF the
  flaky external drive): `docker run -d --name riparian-pg-stable -p 55432:5432 -v
  ~/riparian-pgdata-stable:/var/lib/postgresql/data postgis/postgis:16-3.4`; C# API on :5237; frontend
  `VITE_API_URL=http://localhost:5237 npm run dev` (:3000). Layers with data draw (streams, buffers,
  parcels, wetlands, riparian-extent RF + NMRipMap); parcels sit east of the old center (recenter fixed).
- **Docker zombie:** the `riparian-pg-stable` container can get stuck (external-drive containerd
  `meta.db: input/output error` → `docker stop/rm` no-op). Fix = restart Docker Desktop. Do NOT keep
  hammering docker against the failing store, and NEVER start the external-drive Aspire/Docker stack.

## Where we are

Pivoting the riparian POC into a portfolio piece for the Ai2 "AI for the Planet" Senior SWE
role. Renamed → **san-juan-riparian-watch** (GitHub repo renamed by user; local remote update
+ branch push still PENDING). README fully rewritten to the delineation/health/change framing.
Three tracks now.

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
5. **OlmoEarth — re-run via Ai2's own `olmoearth_projects` recipe (HIGH VALUE, 2026-07-11).**
   Our "RF 0.73 beat OlmoEarth-Nano 0.46" result is very likely measuring **our harness, not
   the model**. Ai2's published [`mangrove`](https://github.com/allenai/olmoearth_projects)
   project is a near-exact analog of Stage 1 (segment woody vegetation near water from an S2
   time series, validated against an authoritative reference map — GMW there, **NMRipMap**
   here) and it does four things we did not:
   - `OLMOEARTH_V1_BASE`, not Nano;
   - **fine-tunes the backbone** (`FreezeUnfreeze`, unfreeze @ epoch 20 at 10× LR) instead of
     freezing it behind a **sklearn RandomForest head**;
   - **12 monthly S2 mosaics** (`period_duration: 30d`, `min_matches: 12`) vs our
     `max_timesteps=5`;
   - a real `SegmentationPoolingDecoder`, instead of **mean-pooling tokens over time AND
     band-sets** — which discards the phenology signal that *is* the riparian discriminator.
   Reported mangrove accuracy: 97.6%. **Scaffold committed at
   `olmoearth_run_data/riparian_extent/`** (`dataset.json` / `model.yaml` / `olmoearth_run.yaml`,
   transcribed from `mangrove`, NMRipMap as label source, spatial split). Needs a GPU +
   `olmoearth_projects` checkout to run. Note **v1.1 cuts compute ~3×** (band-merged tokens)
   and **v1.2 adds RoPE** — re-check whether a smaller variant is viable first.
   Either outcome is publishable; the current comparison is not a fair test. Tracked as an issue.
   Then: baseline-vs-OlmoEarth disagreement maps.
6. **Web app** — frontend map layer for extent (endpoint exists) + reach summaries.

## Environment notes
- ETL host env is polluted (pandas bumped to 3.0.3 by odc-stac; a broken `vision` nspkg
  warning is cosmetic). The real ETL runs in Docker; new delineation deps installed on host
  for verification. Consider a dedicated venv.
- Dead upstream endpoints: repo's `NLCD_EROS_URL` (HTML) + LANDFIRE `US_250EVT` (404) — the
  delineation labels no longer use them (STAC land-cover instead); the *existing* NLCD/LANDFIRE
  ETL steps may need the same repointing.
