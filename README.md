# San Juan Riparian Watch

> 📄 **[Engineering & methodology walkthrough](https://emeraldleaf.github.io/san-juan-riparian-watch/engineering-review.html)** — how the pipeline works end to end, with verbatim code and the weak points to scrutinize.

Basin-scale **riparian vegetation delineation, health scoring, and change monitoring** for
the San Juan River watershed (Colorado + New Mexico). It learns *where riparian vegetation
actually is* from satellite time series — instead of assuming a fixed distance from a
stream — then scores that vegetation's condition (including invasive tamarisk / Russian
olive cover) and tracks how it changes over the long Earth-observation record.

The stack is a STAC Earth-observation ETL, a PostGIS spatial database, a Python ML package
(a RandomForest baseline measured head-to-head against the **OlmoEarth** foundation model),
a .NET Aspire-orchestrated C# REST API, and a React + MapLibre map frontend.

> ### How this is built is part of the contribution
>
> **[The method](docs/method.md)** — AI-assisted research that catches its own errors. The dangerous
> failure of LLM-assisted work is not hallucinated code (a compiler catches that); it is a **retracted
> result still published as fact**, a model **scored against 45%-wrong labels**, a **novelty claim a
> 2018 paper already falsified**. Those compile, pass tests, and read beautifully.
>
> So the rules are **mechanical, not exhortative**: a retraction registry that makes CI fail any doc
> still asserting a withdrawn claim; tombstones for retired values; `/paper-audit`, which attacks our
> own novelty claims and has **narrowed three of them**; and a control experiment run before the
> interesting one. Every gate was verified by making it **fail** on real historical drift.
>
> It also records what didn't work — **every documentation-only surface drifted**, including an
> "enforcement" agent that was invoked by nothing for the life of the repo.

> ### What is actually new here — the time axis
>
> Riparian extent for **one epoch** is already solved: CO-RIP (Woodward et al. 2018) mapped the
> whole Colorado Basin, San Juan included, at median κ 0.80. Building another RF extent classifier
> is not a contribution, and this repo says so.
>
> **But nothing existing is annual.** CO-RIP is one raster; NMRipMap is one 2020 map. CSU/NREL
> (Evangelista et al. 2018) went furthest — riparian-vegetation maps for **2006, 2016 and the change
> between them**, and Russian-olive maps **on the San Juan for those two years** — but that is **two
> epochs, at 30 m, on two different sensors**, and they report that **Landsat cannot resolve the
> tamarisk phenological signature** and that **beetle defoliation confounded their models**.
> **Nobody has an annual, 10 m, beetle-aware riparian product for this basin — of extent *or* of
> species.**
>
> So the goal is the **time axis**: match the authoritative reference for one epoch as
> *calibration*, then run the model across the Earth-observation record to produce
> **riparian extent over time** and **native-vs-invasive cover over time** — spread, retreat, and
> change at reach scale.
>
> That also cracks a problem we had written off. The tamarisk beetle (*Diorhabda*) was released on
> the San Juan in **2004–07**, and defoliated *Tamarix* **browns early** — inverting the
> late-senescence signal the entire detection literature depends on. There is no un-confounded
> *place* left in the basin. But Landsat's record starts in **1984**: there is a **twenty-year
> un-confounded *time***. See
> [the fine-tune ADR](docs/decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md).

[![ci-python](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-python.yml/badge.svg)](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-python.yml)
[![ci-dotnet](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-dotnet.yml/badge.svg)](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-dotnet.yml)
[![ci-frontend](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-frontend.yml/badge.svg)](https://github.com/emeraldleaf/san-juan-riparian-watch/actions/workflows/ci-frontend.yml)

---

## Table of Contents

- [The Problem: Why Not Fixed Buffers](#the-problem-why-not-fixed-buffers)
- [The Three-Stage Pipeline](#the-three-stage-pipeline)
- [What's Built Today](#whats-built-today)
- [How Delineation Works](#how-delineation-works)
- [Study Area](#study-area)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [API Endpoints](#api-endpoints)
- [Database & Medallion Architecture](#database--medallion-architecture)
- [Testing & CI](#testing--ci)
- [Engineering Method (Encoding Loop)](#engineering-method-encoding-loop)
- [Getting Started](#getting-started)
- [Commands Reference](#commands-reference)
- [Data Sources](#data-sources)
- [Observability](#observability)
- [Code Quality (SonarQube)](#code-quality-sonarqube)
- [Roadmap](#roadmap)

---

## The Problem: Why Not Fixed Buffers

The project began as a buffer-compliance POC: define "riparian" as a fixed 30.48 m (100 ft)
buffer around every stream centerline, then score vegetation inside it. That encodes a false
assumption. In the semi-arid San Juan Basin, riparian zones are controlled by geomorphology,
water-table access, and actual phreatophyte vegetation (cottonwood, willow — and invasive
tamarisk / Russian olive), **not by distance from a line**. Many buffered pixels are dry
upland; many real riparian strips fall outside any fixed buffer. Every downstream product —
health, compliance, the "unhealthy riparian" map — inherits that error.

So the project was reframed ([ADR](docs/decisions/2026-07-03-delineation-over-hydrology-buffers.md)):
**delineate riparian extent as a learned map first**, with a per-pixel confidence layer,
then build condition and change on top of a correct extent. This mirrors the applied
remote-sensing literature — Pace et al. 2022 (*Ecological Indicators* 144:109519) compute
vegetation indices only on "pure riparian pixels" identified from land cover, precisely to
avoid the mixed-pixel error a fixed buffer bakes in.

> The original buffer-era ETL (streams → buffers → parcel compliance → NDVI/NLCD/LANDFIRE/
> SSURGO/LiDAR enrichment → SMP health grades) still exists and runs — it's the A/B baseline
> the learned pipeline is measured against. `generate_buffers()` was demoted from *foundation*
> to *comparison*.

---

## The Three-Stage Pipeline

| Stage | Product | Status |
|-------|---------|--------|
| **1 — Delineate** | *Where* is riparian vegetation? A learned extent map + per-pixel probability, plus per-reach `%riparian_cover`. | **Built & validated** (baseline slice end-to-end) |
| **2 — Score condition** | *How healthy* is it? Greenness + moisture + persistence + structure, penalized by invasive (tamarisk / Russian olive) cover. | Specced; invasive labeling module built |
| **3 — Detect change** | *How is it changing?* Annual extent gain/loss + health delta + invasive spread over the longest feasible record (Landsat 1982+ → Sentinel-2/HLS). | [Specced](docs/specs/2026-07-04-stage3-annual-change.md), phased |

Each stage's design is captured as a spec in [`docs/specs/`](docs/specs/) and material decisions
as ADRs in [`docs/decisions/`](docs/decisions/). The live state of the build is tracked in
[`docs/STATUS.md`](docs/STATUS.md).

---

## What's Built Today

The **Stage-1 baseline vertical slice runs end-to-end against the live database**:

```
STAC datacube  →  multitemporal features  →  weak labels        →  RandomForest
(S2 L2A over    (NDVI/EVI/NDMI/NDRE/kNDVI   (WorldCover ∧ io-lulc    (spatial CV)
 the AOI)        + terrain, per season)      "woody-near-water"          │
                                             ∧ NWI)                      ▼
                                                              vectorize → silver.riparian_extent
                                                              served via GET /api/riparian/extent
```

**First verified run** (documented in [STATUS.md](docs/STATUS.md)): ~102k weak-labeled samples,
**spatial-CV ROC-AUC ≈ 0.90 / precision ≈ 0.81**, riparian polygons written to
`silver.riparian_extent` and served as a MapLibre layer.

The honest result is **stratified**: delineation is excellent on broad lowland alluvial
reaches (e.g. Malpais Arroyo–San Juan River) and hardest in narrow headwaters and the
agricultural valley interface, where the corridor is a few pixels wide and irrigated crops
mimic phreatophyte phenology. That reliability-varies-by-stream-order story — stated, not
hidden — is the point: the model ships with a confidence layer, spatial-CV metrics, and
independent reference-layer validation, not a single inflated accuracy number.

Also landed: a **HAND (Height Above Nearest Drainage)** valley-bottom envelope (Stage 1A),
a **per-reach** processor (NHD flowlines → ~250 m reaches → `%riparian_cover`), an
**invasive-species** labeling module (NMRipMap → tamarisk / Russian-olive labels), an
**OlmoEarth** embedding scaffold (the foundation-model contender), and **reference-layer
validation** against NMRipMap (NM) with CO-RIP planned for Colorado.

> **On the OlmoEarth result: the published RF-beats-the-foundation-model number is retracted.**
> It was scored against ground truth that was ~45% wrong, with the model's time axis averaged away,
> against imagery four years newer than the labels. The obvious fix — restore the time axis — was
> tested and **did not explain the gap**. The twist is that the corrupted labels had been
> *flattering* the foundation model, not handicapping it. What remains untested is OlmoEarth **as
> Ai2 actually uses it** (fine-tuned `BASE` + `SegmentationPoolingDecoder`, not a frozen Nano
> feeding a scikit-learn RandomForest). Full story, with the numbers:
> [OlmoEarth vs the RF baseline](docs/olmoearth-vs-rf-baseline.md).
>
> **Label vintage matters:** NMRipMap v2.0 Plus was photo-interpreted from **NAIP 2020**, so models
> are fit on **2020** imagery and may *predict* any year. Fitting 2020 labels against 2024
> reflectance is label noise you inflict on yourself.

---

## How Delineation Works

The Stage-1 pipeline (Python `riparian/` package) is network-first and multi-evidence.

**1A — Candidate envelope (physics first).** `riparian/delineation/hand.py` derives a
HAND / valley-bottom mask from the 3DEP DEM: low HAND = hydrologically connected valley
bottom where riparian vegetation *can* exist. This constrains inference and eliminates
uplands early, cutting false positives and compute — the physically-motivated replacement
for the fixed buffer as the "container".

**1B — EO delineation inside the envelope.** `riparian/datacube/stac.py` turns a STAC query
(AOI + time window + cloud filter) into an analysis-ready multitemporal `xarray` cube via
`odc-stac` — the data-selection step becomes queryable and auditable instead of manual
per-scene downloads. `riparian/datacube/features.py` builds the per-pixel feature stack:
per-season spectral indices (NDVI, EVI, NDMI SWIR-moisture, NDRE red-edge, kNDVI) plus
terrain. Dry-season contrast is the phreatophyte discriminator — groundwater-subsidized
vegetation stays green when uplands brown off.

**1C — Weak-label fusion.** `riparian/delineation/weak_labels.py` builds training labels from
the *agreement* of independent land-cover products sampled on the Sentinel-2 grid — ESA
WorldCover ∧ Impact-Observatory io-lulc "woody-near-water" ∧ NWI wetlands. Agreement is the
supervision signal; it is deliberately **not** the definition (avoiding "green near water =
riparian"). There is no field data — that's the stated ceiling on "reliable".

**Models — baseline vs. foundation model.** `riparian/delineation/baseline.py` trains a
scikit-learn RandomForest on the feature stack (the label-efficient, literature-standard
baseline; XGBoost is a drop-in when `libomp` is present). `riparian/delineation/olmoearth.py`
extracts **OlmoEarth** multimodal embeddings as features for the same task, so the two run on
the same labels and validation harness and can be diffed with agreement/disagreement maps —
the portfolio's core ML story.

**Validation — spatial, not random.** Riparian training data is strongly spatially
autocorrelated, so a random train/test split leaks (a test pixel's neighbors are in the
training set). `riparian/delineation/validate.py` blocks the study area into spatial tiles and
holds out whole tiles per fold (GroupKFold on tile id) — the defensible way to estimate
generalization. `riparian/validation/reference.py` adds an *independent* check against
NMRipMap v2.0+ (queried live from its ArcGIS MapServer), stratified by stream order / valley
type, with NM and CO validated separately to respect their different source methodologies.

**Orchestration.** `riparian/delineation/runner.py::run_delineation()` ties the verified
pieces into one run and writes `silver.riparian_extent` (+ persists the weak-labeled samples
to `bronze.riparian_training_samples` for reproducibility). `riparian/reaches/processor.py`
produces the manager-facing per-reach product into `gold.reach_riparian`.

---

## Study Area

**AOI = the San Juan River hydrologic watershed (HUC 1408), Colorado + New Mexico**,
headwaters → lowlands. The organizing unit is the **HUC12** (each an independently
processable, restartable tile); river segmentation is **NHD flowlines split into ~250 m
reaches**. Development runs subset-first on three representative tiles (verified against the
USGS Watershed Boundary Dataset):

| Tile (HUC12) | Character | Location |
|--------------|-----------|----------|
| `140801010401` Turkey Creek | Headwaters | CO |
| `140801041003` Tucker Canyon–Animas River | Mid-valley / ag interface | NM |
| `140801051001` Malpais Arroyo–San Juan River | Lowland / alluvial | NM |

Storage CRS is **EPSG:4269 (NAD83)** throughout; all metric math casts to `geography`.

---

## Architecture

```
                         ┌───────────────────────────────────┐
                         │        .NET Aspire AppHost         │
                         │  (orchestration, DI, OpenTelemetry)│
                         └──────────────┬────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
 ┌────────▼─────────┐        ┌──────────▼──────────┐       ┌──────────▼──────────┐
 │  Python ETL      │        │   C# REST API       │       │  React Frontend     │
 │                  │        │                     │       │  (MapLibre GL)      │
 │  riparian/       │        │  Endpoints (thin)   │       │                     │
 │   datacube/      │        │    ↓                │       │  - riparian extent  │
 │   delineation/   │        │  Services (SQL +    │       │  - reach summaries  │
 │   health/        │        │   ActivitySource)   │       │  - buffer layers    │
 │   reaches/       │        │    ↓                │       │  - NDVI / grades    │
 │   validation/    │        │  Repository (Dapper │       │  - timelapse slider │
 │                  │        │   + GeoJSON/MVT)    │       │                     │
 │  STAC / ML       │        │                     │       │  session tracking   │
 └────────┬─────────┘        └──────────┬──────────┘       └──────────┬──────────┘
          │ writes                      │ reads (all schemas)         │ HTTP + GeoJSON
          │                             │                             │
          └──────────────► ┌────────────▼─────────────┐ ◄────────────┘
                           │   PostgreSQL + PostGIS    │
                           │                           │
                           │  bronze  raw ingest       │  streams, parcels, wetlands, soils,
                           │          + training samples│  nhd_flowlines, riparian_training_samples
                           │  silver  spatial + learned│  riparian_extent, buffers, compliance,
                           │                           │  vegetation_health, intersections
                           │  gold    analytics        │  reach_riparian, summaries, health scores
                           │  meta    ETL run tracking │
                           └───────────────────────────┘
```

| Service | Role | Port |
|---------|------|------|
| **Aspire AppHost** | Orchestrates containers, injects connection strings, manages lifecycle | Dashboard: 18888 |
| **PostgreSQL + PostGIS** | Shared spatial database (persistent bind-mount) | 5432 |
| **C# REST API** | Reads all schemas, returns GeoJSON/MVT via service → repository (Dapper) | 8000 |
| **Python ETL / ML** | Writes bronze/silver/gold; STAC datacube + delineation | batch |
| **React frontend** | MapLibre map, calls the API with session tracking | 3000 |

The API follows a strict **endpoint → service → repository** layering (thin handlers, SQL in
services, a generic Dapper repository). An [ADR](docs/decisions/2026-07-04-nextaurora-rules-applicability.md)
records why `IPostGisRepository` is a legitimate abstraction here (Dapper is a raw query
executor, not EF's `DbContext`/`DbSet` unit-of-work — so the repository earns its keep as the
mock seam for unit tests and as the owner of GeoJSON/MVT building).

---

## Repository Structure

```
san-juan-riparian-watch/
├── RiparianPoc.AppHost/               # .NET Aspire orchestrator (entry point)
├── RiparianPoc.Api/                   # C# REST API
│   ├── Endpoints/GeoDataEndpoints.cs  #   Thin route handlers + DTO records
│   ├── Services/                      #   ISpatialQueryService + IComplianceDataService (SQL + logic)
│   ├── Repositories/                  #   IPostGisRepository — Dapper + GeoJSON/MVT
│   ├── Middleware/                    #   Correlation/session + global exception handling
│   └── Models/                        #   ApiErrorResponse
├── RiparianPoc.Api.Tests/             # xUnit + NSubstitute (service validation, mocked repo)
├── RiparianPoc.ServiceDefaults/       # Shared Aspire config (OTEL, resilience, discovery)
│
├── python-etl/
│   ├── riparian/                      # ── Modern domain package (Stage 1+) ──
│   │   ├── datacube/                  #   stac.py (odc-stac cube) · features.py (index/terrain stack)
│   │   ├── delineation/               #   hand.py · weak_labels.py · baseline.py (RF) ·
│   │   │                              #   validate.py (spatial CV) · olmoearth.py (FM) · runner.py
│   │   ├── health/invasive.py         #   tamarisk / Russian-olive labels from NMRipMap
│   │   ├── reaches/processor.py       #   NHD flowlines → ~250 m reaches → %riparian_cover
│   │   └── validation/reference.py    #   NMRipMap / CO-RIP reference validation
│   ├── tests/                         #   pytest (pure-function unit tests)
│   ├── etl_pipeline.py                # ── Legacy buffer-era ETL (A/B baseline) ──
│   ├── ndvi_processor.py              #   Sentinel-2 NDVI + health scoring
│   ├── nlcd_processor.py, landfire_processor.py, ssurgo_processor.py,
│   ├── lidar_processor.py, raster_processor.py, health_scorer.py
│   ├── entrypoint.py                  #   full/incremental/ndvi/all/scheduled dispatcher
│   ├── requirements.txt               #   full runtime deps
│   └── requirements-test.txt          #   curated CI subset (no torch/geopandas)
│
├── frontend/                          # React 18 + TypeScript + MapLibre GL + Tailwind (Vite)
│
├── sql/                               # Additive migrations (create_schemas.sql = source of truth)
│   ├── create_schemas.sql             #   base bronze/silver/gold schema
│   ├── delineation_migration.sql      #   silver.riparian_extent + bronze.riparian_training_samples
│   ├── reach_migration.sql            #   bronze.nhd_flowlines + gold.reach_riparian
│   └── nwi/raster/ssurgo/lidar/health/incremental_migration.sql
│
├── docs/
│   ├── STATUS.md                      #   cross-session live state
│   ├── specs/                         #   Stage-1, Stage-3 feature specs
│   ├── decisions/                     #   ADRs (delineation-over-buffers, NextAurora-rules)
│   ├── sonarqube.md                   #   full SonarQube setup guide
│   └── riparian-pipeline.{excalidraw,svg,png}   # paired architecture diagram
│
├── .github/workflows/                 # ci-python · ci-dotnet · ci-frontend · encoding-loop
├── .claude/                           # encoding-loop method (commands, skills, agents)
├── dev.sh                             # all-in-one dev script
├── CLAUDE.md                          # AI-assistant + contributor conventions (lean canon)
└── RiparianPoc.sln
```

> The `.NET`/frontend projects keep their original `RiparianPoc.*` names — only the GitHub
> repository and product were renamed to *San Juan Riparian Watch*.

---

## Tech Stack

**ETL / ML (Python 3.11+)** — `odc-stac` + `pystac-client` + `planetary-computer` (STAC
datacube), `xarray` / `rasterio` (raster), `scikit-learn` (RandomForest baseline), OlmoEarth
+ `torch` (foundation-model track), `shapely` / GeoPandas (vectorize + PostGIS I/O),
SQLAlchemy `text()` (parameterized SQL), `pysheds` (HAND). Weak labels from ESA WorldCover +
io-lulc + NWI.

**API (.NET 10)** — ASP.NET Core minimal APIs, .NET Aspire 13 (orchestration + OpenTelemetry),
Dapper (micro-ORM, `NpgsqlDataSource`), NetTopologySuite (GeoJSON), OpenTelemetry tracing.

**Database** — PostgreSQL 16 + PostGIS 3.4 (GiST-indexed geometry, `geography` metric math).

**Frontend** — React 18, TypeScript, **MapLibre GL** via `react-map-gl`, Tailwind CSS, Vite.
(Migrated from Leaflet; some legacy NDVI-heatmap components remain from the buffer era.)

**Quality** — pytest, xUnit + NSubstitute, ruff + mypy, `dotnet format`, SonarQube, GitHub
Actions CI, CodeRabbit review.

---

## API Endpoints

All spatial endpoints return **GeoJSON FeatureCollections**; errors return a structured
`ApiErrorResponse` (see [Observability](#observability)).

### Learned delineation (Stage 1)

| Endpoint | Description |
|----------|-------------|
| `GET /api/riparian/extent` | Learned riparian extent + probability from `silver.riparian_extent` (`?method=rf\|olmoearth`) |

### Buffer-era layers (legacy / A/B baseline)

| Endpoint | Description |
|----------|-------------|
| `GET /api/streams` | Stream centerlines (comid, gnis_name, stream_order) |
| `GET /api/buffers` | Fixed 30.48 m buffers (stream_id, area_sq_m) |
| `GET /api/buffers/health` · `/health/{date}` | Buffers with latest / dated NDVI health |
| `GET /api/buffers/scores` | Buffers with SMP composite health grades (A–F) |
| `GET /api/parcels` · `/focus-areas` | Parcels with compliance / encroachment status |
| `GET /api/wetlands` · `/soils` | NWI wetland / SSURGO soil polygons |
| `GET /api/buffers/{id}/wetlands\|landcover\|vegetation-structure\|soils\|canopy\|score` | Per-buffer enrichment detail |
| `GET /api/vegetation/buffers/{id}` · `/api/ndvi/dates` | NDVI time series / acquisition dates |
| `GET /api/summary` | Gold-layer compliance + grade summary |

---

## Database & Medallion Architecture

Data flows one direction — **bronze → silver → gold** — and never writes back upstream.

| Layer | Schema | Purpose | Key tables |
|-------|--------|---------|-----------|
| **Bronze** | `bronze` | Raw ingest, minimal transform | `streams`, `parcels`, `nwi_wetlands`, `ssurgo_soils`, `nhd_flowlines`, `riparian_training_samples` |
| **Silver** | `silver` | Spatial + learned processing | `riparian_extent` (learned), `riparian_buffers`, `parcel_compliance`, `vegetation_health`, `buffer_*` intersections |
| **Gold** | `gold` | Aggregated analytics | `reach_riparian` (per-reach `%cover`), `riparian_summary`, `buffer_health_score` |
| **Meta** | `meta` | ETL run tracking / audit | `etl_runs` |

`sql/create_schemas.sql` is the schema source of truth; every later change is an **additive**
`*_migration.sql` (never an edit to the base file). Every geometry column has a GiST index;
spatial joins use a `&&` bounding-box pre-filter before exact `ST_Intersects`.

---

## Testing & CI

| Suite | What it covers | How to run |
|-------|----------------|-----------|
| **Python** (pytest) | Pure-function unit tests: spectral indices, spatial-fold grids, weak-label logic, validation math | `cd python-etl && pytest -m "not live"` |
| **C#** (xUnit + NSubstitute) | Service-layer validation + behavior with a mocked `IPostGisRepository` | `dotnet test RiparianPoc.Api.Tests/` |
| **Frontend** | `tsc` + Vite build gate; ESLint | `cd frontend && npm run build` |

Four GitHub Actions workflows run on pull requests (path-filtered, concurrency-cancel):

- **`ci-python`** — ruff (gate) → mypy (advisory) → pytest (gate), using the curated
  `requirements-test.txt` so CI stays fast (no torch/GDAL).
- **`ci-dotnet`** — restore → build → `dotnet test` (gate) → `dotnet format --verify` (advisory),
  scoped to the API test project (not the Aspire AppHost).
- **`ci-frontend`** — `npm ci` → build (gate) → lint (advisory).
- **`encoding-loop`** — lean-canon + doc/diagram-pairing checks for the AI workflow.

`live`-marked tests (real STAC / DB) are skipped in CI and run locally against Planetary
Computer + PostGIS.

---

## Engineering Method (Encoding Loop)

This repo dogfoods a portable **encoding-loop method** (ported from a private DDD codebase and
retuned to this system's actual architecture): project rules are encoded across five surfaces —
`CLAUDE.md` + `.claude/`, `.coderabbit.yaml`, an `architecture-reviewer` agent, commands +
skills, and `docs/` + a paired diagram — across three enforcement tiers, kept from drifting by
mechanical git hooks (a lean-canon budget on `CLAUDE.md`, doc↔diagram pairing, and a
stale-reference audit on `git mv`). Feature work starts from a `/feature-spec` (value gate →
acceptance criteria → affects → ADR trigger) that lands in `docs/specs/`. The intent: keep an
AI-assisted codebase coherent and reviewable as it scales, and make architectural divergences
*conscious decisions* (recorded as ADRs) rather than drift.

---

## Getting Started

### Prerequisites

- **macOS** (the project runs from an external drive — see below)
- **Docker Desktop** — configured to store data on the external drive
- **.NET 10 SDK** · **Node.js 20+** · **Python 3.11+**
- **External drive** mounted at `/Volumes/Mac OS Extended 1/`

> **External-drive note.** This repo and its Docker data live on an external drive. Verify it's
> mounted (`ls "/Volumes/Mac OS Extended 1/"`) before starting anything. `dev.sh` runs a
> drive-I/O probe on startup and provides `--reconnect` recovery + `--backup`/`--restore` for
> the database, because Docker on an external drive restarts often.

### Quick Start

```bash
cd "/Volumes/Mac OS Extended 1/riparian-poc"

./dev.sh              # start everything (drive check → PostGIS → Aspire → API → frontend)
./dev.sh --status     # health + drive I/O + data counts (incl. NDVI)
```

| Service | URL |
|---------|-----|
| Frontend (map) | http://localhost:3000 |
| Aspire Dashboard | http://localhost:18888 |
| API / Swagger | http://localhost:8000 · http://localhost:8000/swagger |

The learned delineation pipeline runs from the Python package —
`riparian.delineation.runner.run_delineation(...)` — against Planetary Computer STAC + the
live PostGIS. The legacy buffer-era ETL runs via `./dev.sh --update` (see below).

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `./dev.sh` | Start all services |
| `./dev.sh --status` | Health of all services + data counts |
| `./dev.sh --stop` / `--restart` | Stop / restart (PostGIS persists its data) |
| `./dev.sh --reconnect` | Recover after an external-drive disconnect |
| `./dev.sh --backup` / `--restore` | Snapshot / restore the database (`pg_dump -Fc`) |
| `./dev.sh --update [incremental\|ndvi\|full]` | Legacy buffer-era ETL (default incremental; preserves NDVI) |
| `./dev.sh --sonar` / `--sonar-stop` | Start / stop the SonarQube server |
| `./dev.sh --lint` / `--lint-dotnet` | Static analysis (Python+TS+SQL / C#) |

```bash
dotnet build RiparianPoc.sln          # build all .NET projects
dotnet test RiparianPoc.Api.Tests/    # C# unit tests
cd python-etl && pytest -m "not live" # Python unit tests
cd frontend && npm run dev            # frontend dev server
```

> **Never** kill Aspire processes directly — it can restart the PostgreSQL container and
> corrupt data. Always use `./dev.sh --stop`.

---

## Data Sources

All are free and require no API key.

| Source | Access | Provides |
|--------|--------|----------|
| **Sentinel-2 L2A / Sentinel-1 RTC** | STAC (Planetary Computer) | Optical + SAR time series for delineation |
| **Landsat C2 L2 / HLS** | STAC (Planetary Computer) | Long-record (1982+) trend backbone for change |
| **ESA WorldCover / io-lulc-9-class** | STAC (Planetary Computer) | Weak-label land-cover agreement |
| **3DEP DEM (seamless / cop-dem-glo-30)** | STAC (Planetary Computer) | Terrain + HAND envelope |
| **3DEP LiDAR (DSM/DTM)** | STAC (Planetary Computer) | Canopy height structure |
| **NHDPlus V2.1 / NHD flowlines** | ArcGIS REST (USGS / National Map) | Stream network + reach segmentation |
| **NWI Wetlands** | ArcGIS REST (FWS) | Wetland weak-label signal |
| **NMRipMap v2.0+** | ArcGIS MapServer (NHNM) | NM reference-riparian validation + invasive labels |
| **CO-RIP** | Dryad dataset | CO reference-riparian validation (planned) |
| **Colorado Public Parcels / SSURGO / NLCD / LANDFIRE** | ArcGIS / WFS / WCS | Legacy buffer-era enrichment |

Study area: San Juan River watershed, HUC 1408 (subbasin 14080101).

---

## Observability

The API has built-in distributed tracing, structured logging, and layered error handling via
**OpenTelemetry** + **.NET Aspire**.

- **Correlation & session tracking** — middleware extracts `X-Correlation-Id` (or W3C TraceId)
  and `X-Session-Id`, tags the trace, and wraps downstream logs in a scope so every entry
  carries `CorrelationId` / `SessionId` / `ClientIp`. The frontend generates a session id per
  page load and sends it on every fetch. Filter Aspire Dashboard traces by `session.id` to see
  one user's whole session.
- **Nested spans** — three custom `ActivitySource`s produce `HTTP → Service → Repository →
  Npgsql` span hierarchies visible in the dashboard.
- **Defense-in-depth errors** — the repository catches `NpgsqlException` (enriches trace +
  rethrows); services validate input (`ArgumentException`); a global middleware maps exception
  types to HTTP status (`NpgsqlException`→503, `ArgumentException`→400, `KeyNotFoundException`→404,
  `OperationCanceledException`→504, else 500) and returns a structured `ApiErrorResponse`
  (`detail` only in Development).

---

## Code Quality (SonarQube)

Static analysis for Python / TypeScript / SQL / C# runs against a local SonarQube Community
server (Docker). Quick start:

```bash
./dev.sh --sonar          # start the server (http://localhost:9000)
./dev.sh --lint           # scan Python + TypeScript + SQL (needs SONAR_TOKEN in .env)
./dev.sh --lint-dotnet    # scan C# via dotnet-sonarscanner
```

Full setup, VS Code connected mode, replication for other projects, and troubleshooting live in
**[docs/sonarqube.md](docs/sonarqube.md)**.

---

## Roadmap

Tracked live in [`docs/STATUS.md`](docs/STATUS.md). Near-term:

1. **HUC12 tiling** — per-tile, restartable delineation across the three locked tiles, then scale.
2. **Stage 1A wiring** — HAND envelope constraining inference basin-wide.
3. **Per-reach rollups** — `gold.reach_riparian` populated for "which reaches are riparian /
   degrading", with confidence + quality flags.
4. **Reference validation** — NMRipMap (NM) + CO-RIP (CO), IoU/F1 stratified by stream order,
   validated per state then reconciled at the seam.
5. **OlmoEarth everywhere** — GPU embedding store + head training + baseline-vs-FM disagreement maps.
6. **Stage 2 / Stage 3** — condition score (invasive-penalized) and annual change / invasive-spread
   products on the Landsat 1982+ backbone.

---

*A learned, confidence-aware riparian monitoring platform for the San Juan Basin — extent,
condition, and change from open Earth-observation data.*

---

## Licence — code and data are different

| What | Licence |
|---|---|
| **Source code** | **Apache-2.0** ([`LICENSE`](LICENSE)) |
| **Data products** — models, label layers, extent/invasive rasters, maps | **CC BY-SA 4.0** |

The data products are **not** our choice: this project trains on **CC BY-SA 4.0** datasets (the
CSU/NREL field points, valley bottoms and tamarisk rasters), and **ShareAlike requires adapted material
to carry the same licence.** Training on them is permitted; derived maps must be CC BY-SA.

Attribution and the full reasoning: [`LICENSE-DATA.md`](LICENSE-DATA.md) ·
[`docs/data-licenses.md`](docs/data-licenses.md).
