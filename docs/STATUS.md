# Project Status

**Last updated:** 2026-07-04

Cross-session entry point. Surfaced automatically at session start by the
`inject-status.sh` hook. Refresh with `/sync-status`.

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

### Track 3 — Document Intelligence (RAG + map-linked geo citations) — SPEC + Phase-A scaffold
New second surface over the same AOI: Olmo 2 *explains* (RAG Q&A with citations over watershed
docs), OlmoEarth *sees* (EO layers), joined at the map. **Decision: reuse the existing
Re-find Catalog RAG harness** (`~/Dev/AI Course/my-capstone-rag/production-app` — Haystack 2.0 +
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
- **Env caveat:** the riparian PostGIS host-port zombies repeatedly on the external drive (Docker
  drops the binding / container goes exec-dead). The server **degrades gracefully** (`geo_available`
  flag) — RAG+citations work regardless; geo populates when the DB is healthy. Consider moving PG
  off the external drive for a stable demo.
- **Next:** `/docs/for-area` reverse lookup + ingest-time `docs.chunk_geo_mentions` tagging +
  **frontend** (MapLibre Q&A panel → highlight `resolved_geometries`) — best done with a stable DB.

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
