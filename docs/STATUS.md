# Project Status

**Last updated:** 2026-07-12

Cross-session entry point. Surfaced automatically at session start by the
`inject-status.sh` hook. Refresh with `/sync-status`.

## Current state — git, PRs, and WHY things are where they are (2026-07-12)

**READ THIS FIRST if you are a coding agent picking up the repo.**

### Branches
- Working tree is on **`main`**. The ETL/label work merged via **PR #13** (`a0bb842`): the 3 HIGH
  ETL fixes, the NMRipMap class crosswalk, SMP scoring, the OlmoEarth task scaffold, and the
  25-source corpus (`docintel/corpus/seed_sources.yaml`).
- `feat/docintel-private-split` and `feat/etl-fixes-and-labels` are both **fully merged into
  `main`** and superseded. Do not build on them.

### GitHub Pages — LIVE
Built from `main`/`docs` (legacy Jekyll). Hub at
`https://emeraldleaf.github.io/san-juan-riparian-watch/` links the engineering review, literature
review, all specs and ADRs. `docs/_config.yml` declares **`jekyll-optional-front-matter`** — this is
load-bearing: none of the specs/ADRs have YAML front matter, and without that plugin Jekyll skips
them and every link 404s. Do not remove it, and do not re-add `docs/.nojekyll` (it makes Jekyll skip
the whole build, serving the `.md` files as raw text).

### PRs (base = `main`)
- **#3 / #4 / #5 / #10 / #12 / #13 / #14 MERGED.** Pages walkthrough; MVT tile SQL unified into
  `MvtTileSql.Build` + C# xUnit tests; map-UI fixes + soil/wetland popup enrichment; the
  engineering-review corrections; the published docs hub; the ETL/label fixes; the local-config
  cleanup. **#15** (the OlmoEarth fair test) is the last one open.
- **Merge gate:** a PR does not merge until **CodeRabbit's review is green** — not merely its
  check. Its review on #5 caught a real one: `MvtTileSql`'s `^[a-z_]+$` layer guard was
  bypassable, because in .NET `$` also matches *before a trailing newline*, so `"wetlands\n"`
  passed straight into the interpolated SQL literal. Now `\A[a-z_]+\z`. See CLAUDE.md.

### Open issues (base = `main`)
- **#6 / #7 / #8** (the 3 HIGH ETL bugs) and **#11** (NMRipMap labels) — **CLOSED** by PR #13.
- **#9** (OlmoEarth) — **the only open issue, and its premise was tested and DISPROVED.** The
  mean-pooling defect is real (pinned by a unit test), but fixing it moves OlmoEarth-Nano only
  from F1 0.021 -> 0.065 against RF's 0.701. **Pooling does not explain the gap.** The old
  RF 0.73 / OE 0.46 numbers are RETRACTED — they were scored against the ~45%-wrong labels, and
  the corrupted labels were *flattering* the FM (they rewarded predicting corridor membership,
  which a frozen embedding is good at). What is still untested is OlmoEarth **as Ai2 uses it**:
  fine-tuned Base + SegmentationPoolingDecoder, not a frozen Nano + sklearn RF head. That needs
  a GPU. See `docs/olmoearth-vs-rf-baseline.md`.
  - **Plan of record (ADR 2026-07-12, revised):** **the contribution is the TIME axis**, for extent
    *and* invasives. Every existing product is one frozen epoch — CO-RIP is a single raster;
    NMRipMap is a single 2020 map. **Nobody has an annual riparian product for this basin, of
    extent or of species.** So: Step 1 **extent** (calibration control) → Step 2 **invasives**
    (species head) → **Step 3: run it across the archive** — annual extent trajectories + annual
    native-vs-invasive cover/spread. Matching CO-RIP for one epoch is not the deliverable; it is
    the calibration that makes the time series trustworthy.
    **Gate: if extent lands well below the pixel-level RF baseline, STOP and debug — do not
    proceed.**
  - **The beetle has no un-confounded PLACE — but it does have an un-confounded TIME.** OlmoEarth
    supports `LANDSAT` (record from **1984**) and `NAIP`, not just Sentinel-2 (from 2015-10).
    *Diorhabda* was released **2004–07**, so a Landsat series spans a **~20-year pre-beetle era**
    where late-senescence holds uncontaminated. That is the only way to separate "Tamarix senesces
    late" from "defoliated Tamarix browns early". Sensor choice (S2 10 m / ~10 yr vs Landsat 30 m /
    ~40 yr) is decided **after** Step 1, on evidence — 30 m may be too coarse for the corridor.
  - 🔴 **LABEL VINTAGE = 2020 — fit on 2020 imagery.** NMRipMap v2.0 Plus (Muldavin et al. 2023)
    was photo-interpreted from **NAIP 2020**. The 2026-07-12 fair test used **S2 2024** — a 4-year
    gap, i.e. label noise we introduced ourselves. The RF-vs-OlmoEarth *comparison* still stands
    (both arms ate it), but the **absolute numbers are pessimistic**, and it would hurt invasives
    far more than extent (Tamarix cover is exactly what the beetle changes). Predict any year;
    **fit on 2020**.
  - ⚠️ **Two RF baselines exist and they are NOT interchangeable.** Stage-1 delineation is
    **pixel-level (10 m): F1 0.90–0.92**. The fair-test number is **patch-level (80 m): F1 0.701**
    and belongs to the frozen-embedding + RF-head experiment. The fine-tune predicts at
    pixel/segment level, so **compare it to 0.90–0.92** — scoring it against 0.701 would flatter
    it by ~0.2 F1 and manufacture a win.

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
  (Tamarix stays green after natives brown). Our OlmoEarth harness *was* mean-pooling that signal
  away — a real defect, now fixed and unit-tested. **But the 2026-07-12 re-run showed it explains
  only a small part of the RF-vs-FM gap** (F1 0.021 → 0.065 vs RF 0.701), so do not repeat the
  claim that the FM result is "just" a pooling artifact (#9).
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
2. **OlmoEarth flagship — DONE (CPU, 2026-07-06).** Token-mask + square-grid blocker resolved →
   OlmoEarth-v1-Nano encodes end-to-end on CPU. `run_delineation_olmoearth` (FM contender to the
   RF runner) + `docs/olmoearth-vs-rf-baseline.md`: honest 5-fold spatial-CV on a balanced AOI —
   **RF F1 0.73 vs OlmoEarth-Nano F1 0.46** (RF wins in this CPU/Nano/small-AOI setup; FM strengths
   need scale/GPU). Next: basin-scale OlmoEarth on the GPU VM (larger model, full temporal,
   embedding store) + RF-vs-OlmoEarth disagreement maps.
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
