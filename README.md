# Riparian Buffer Compliance POC

A proof-of-concept application that monitors **riparian buffer zone compliance** in the
San Juan Basin (Colorado) using satellite imagery, geospatial analysis, and public land
records. It answers the question: *"Which parcels of land are encroaching on protected
waterway buffer zones, and how healthy is the vegetation in those zones?"*

---

## Table of Contents

- [What This Project Does](#what-this-project-does)
- [Architecture Overview](#architecture-overview)
- [How the Spatial Analysis Works](#how-the-spatial-analysis-works)
- [NDVI Vegetation Health Scoring](#ndvi-vegetation-health-scoring)
- [Data Pipeline (ETL)](#data-pipeline-etl)
- [Incremental Updates](#incremental-updates)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Commands Reference](#commands-reference)
- [API Endpoints](#api-endpoints)
- [Database Schema](#database-schema)
- [Code Quality (SonarQube)](#code-quality-sonarqube)
- [Azure Deployment](#azure-deployment)
- [Troubleshooting](#troubleshooting)
- [Observability](#observability)

---

## What This Project Does

**For Product Managers:** Riparian buffers are strips of vegetation along rivers and
streams that prevent erosion, filter pollution, and protect water quality. Many
jurisdictions require landowners to maintain these buffers — typically 100 feet (30.48
meters) from the stream centerline.

This application:

1. **Pulls stream data** from the National Hydrography Dataset (NHDPlus V2.1) to know
   where every waterway is located in the San Juan Basin.
2. **Generates buffer zones** — 100-foot protective corridors around each stream.
3. **Pulls parcel data** from the Colorado Public Parcels database to know property
   boundaries and ownership.
4. **Identifies focus areas** — any parcel that physically overlaps a buffer zone is flagged.
   The parcel is clipped to the buffer boundary, and the overlap area and percentage of
   buffer encroachment are calculated.
5. **Scores vegetation health** using Sentinel-2 satellite imagery (NDVI) to determine
   whether the vegetation in each buffer zone is healthy, degraded, or bare.
6. **Displays everything on a map** — an interactive web application where you can see
   streams, buffers, parcels (color-coded by compliance), and NDVI heatmaps.
7. **Tracks changes over time** — an incremental update system that checks for new data
   and refreshes only what has changed.

**Current results (San Juan Basin, HUC8 14080101):**
- ~2,000 stream segments monitored
- ~5,000 parcels analyzed
- ~89% compliance rate
- ~167 focus area parcels identified

---

## Architecture Overview

```
                    ┌───────────────────────────────────┐
                    │       .NET Aspire AppHost          │
                    │  (Orchestrates all services)       │
                    └──────────┬────────────────────────┘
                               │
             ┌─────────────────┼─────────────────────┐
             │                 │                      │
    ┌────────▼───────┐  ┌─────▼──────┐  ┌───────────▼──────────┐
    │  Python ETL    │  │  C# REST   │  │  React Frontend      │
    │  Pipeline      │  │  API       │  │  (Leaflet Map)       │
    │                │  │            │  │                      │
    │  - ArcGIS APIs │  │  - GeoJSON │  │  - Stream lines      │
    │  - PostGIS     │  │  - Dapper  │  │  - Buffer polygons   │
    │  - Sentinel-2  │  │  - 6 endpts│  │  - Parcel colors     │
    │  - NDVI calc   │  │  - OTEL   │  │  - NDVI heatmap      │
    └────────┬───────┘  └─────┬──────┘  └───────────┬──────────┘
             │                │                      │
             │         ┌──────▼──────┐               │
             └────────►│  PostgreSQL │◄──────────────┘
                       │  + PostGIS  │    (via API)
                       │             │
                       │  bronze ──► │  Raw data from APIs
                       │  silver ──► │  Buffers, compliance, NDVI
                       │  gold   ──► │  Summary statistics
                       │  meta   ──► │  ETL run tracking
                       └─────────────┘
```

### Service Communication

| Service | Role | Port |
|---------|------|------|
| **Aspire AppHost** | Orchestrates containers, injects connection strings, manages lifecycle | Dashboard: 18888 |
| **PostgreSQL + PostGIS** | Shared spatial database (persistent container) | 5432 |
| **C# REST API** | Reads from all schemas, returns GeoJSON via service layer + Dapper | 8000 |
| **Python ETL** | Writes to bronze/silver/gold schemas | No port (batch job) |
| **React Frontend** | Vite dev server, calls C# API with session tracking | 3000 |

Aspire automatically:
- Starts PostGIS with a persistent container (data survives restarts)
- Injects database connection strings into the API and ETL containers
- Manages startup ordering (PostGIS first, then API, then frontend)
- Provides a dashboard for monitoring all services

---

## How the Spatial Analysis Works

This section explains the core geospatial logic step by step. All spatial operations use
PostGIS, the spatial extension for PostgreSQL.

### Step 1: Identify Streams

The ETL pipeline queries the **NHDPlus V2.1** (National Hydrography Dataset Plus) REST
API for all stream centerlines within the San Juan Basin watershed (HUC8 code 14080101).

Each stream is stored as a **LineString** geometry — a series of connected coordinates
tracing the stream's path. In the database, this looks like:

```
LINESTRING(-107.81 37.28, -107.82 37.29, -107.83 37.30)
```

The pipeline also fetches waterbodies (lakes, reservoirs) and sinks, but buffers are
generated from streams only.

### Step 2: Generate Buffer Zones

For each stream, PostGIS creates a **buffer polygon** — a shape that extends 100 feet
(30.48 meters) outward from every point along the stream centerline.

```sql
ST_Buffer(stream_geom::geography, 30.48)
```

**Why `::geography`?** Coordinates are stored in degrees (EPSG:4269 / NAD83), but buffer
distances need to be in meters. Casting to the `geography` type tells PostGIS to treat
the coordinates as points on Earth's curved surface and measure the buffer distance in
meters. Without this cast, `ST_Buffer(geom, 30.48)` would create a buffer of 30.48
*degrees* — roughly 3,400 kilometers wide.

The result is a polygon that hugs the stream's shape:

```
         Stream (LineString)         Buffer (Polygon)
              │                    ╭──────────────╮
              │                    │    30.48m    │
    ──────────┤──────────  →      │──────┤───────│
              │                    │              │
              │                    ╰──────────────╯
```

### Step 3: Identify Parcel Focus Areas

Next, the pipeline checks every parcel against every buffer to find **overlaps**. This is
the most computationally intensive step, so it uses a two-stage filter:

```sql
FROM bronze.parcels p
JOIN silver.riparian_buffers b
    ON p.geom && b.geom                     -- Stage 1: Bounding box
    AND ST_Intersects(p.geom, b.geom)       -- Stage 2: Exact geometry
WHERE ST_Area(ST_Intersection(...)::geography) > 1  -- Ignore < 1 sq meter
```

**Stage 1 — Bounding box pre-filter (`&&`):** Every geometry has a bounding box (the
smallest rectangle that contains it). The `&&` operator checks whether two bounding boxes
overlap. This is extremely fast because PostGIS stores bounding boxes in a GiST index
(a spatial tree structure). It eliminates ~99% of parcel-buffer pairs that clearly don't
intersect.

```
   Parcel bbox        Buffer bbox
   ┌──────────┐       ┌──────────┐
   │          │       │          │
   │   Parcel │       │  Buffer  │    Bboxes don't overlap → skip
   │          │       │          │    (no expensive calculation needed)
   └──────────┘       └──────────┘
```

**Stage 2 — Exact intersection (`ST_Intersects`):** For the remaining candidates, PostGIS
computes whether the actual polygon shapes touch or overlap. This is slower but precise.

**Computing the overlap:** For every parcel-buffer pair that intersects, the pipeline
clips the parcel to the buffer boundary and calculates metrics on that clipped portion only:

- **Overlap geometry:** `ST_Intersection(parcel, buffer)` — the exact shape of the
  parcel within the buffer (not the full parcel)
- **Overlap area:** `ST_Area(overlap::geography)` — area of the clipped portion in
  square meters
- **Overlap percentage:** overlap area / **buffer** area * 100 — what percentage of the
  buffer zone this parcel encroaches on

Any parcel with more than 1 square meter of overlap is identified as a **focus area**.

### Step 4: Aggregate Compliance Statistics

The gold layer summarizes everything at the watershed level using Common Table
Expressions (CTEs):

- **Total stream length** — sum of all stream segment lengths in meters
- **Total buffer area** — sum of all buffer polygon areas
- **Total parcels** — count of all parcels in the watershed
- **Focus area parcels** — count of parcels identified as focus areas
- **Compliance rate** — (total - focus areas) / total * 100

---

## NDVI Vegetation Health Scoring

**NDVI** (Normalized Difference Vegetation Index) measures how green and healthy
vegetation is using satellite imagery. This project uses free **Sentinel-2** satellite
data from Microsoft's Planetary Computer.

### How NDVI Works

Plants absorb red light for photosynthesis but reflect near-infrared (NIR) light.
Healthy vegetation reflects a lot of NIR and absorbs a lot of red. NDVI captures this
ratio:

```
NDVI = (NIR - Red) / (NIR + Red)
```

| NDVI Value | Meaning | Color on Map |
|------------|---------|--------------|
| > 0.6 | **Healthy** — dense, green vegetation | Dark green |
| 0.3 – 0.6 | **Degraded** — sparse or stressed vegetation | Yellow-orange |
| < 0.3 | **Bare** — little to no vegetation | Red |
| Any (dormant season) | **Dormant** — expected low values outside growing season | Gray |

The San Juan Basin's **peak growing season** is June through August. Only readings from
these months are used for health classification. Outside this window, low NDVI values are
tagged as "dormant" rather than "bare" to avoid false alarms.

### Processing Pipeline

1. **Query Planetary Computer STAC API** for Sentinel-2 L2A images covering each buffer
   zone, filtered to < 20% cloud cover.
2. **Sign the asset URLs** using `planetary_computer.sign_inplace()` (Planetary Computer
   provides free access but requires URL signing).
3. **Clip the satellite raster** to the buffer polygon using `rasterio.mask.mask()` — this
   extracts only the pixels that fall within the buffer boundary.
4. **Calculate NDVI** for each pixel: `(B08 - B04) / (B08 + B04)` where B08 is the NIR
   band and B04 is the red band.
5. **Aggregate statistics** — mean, min, and max NDVI across all pixels in the buffer.
6. **Classify health** based on mean NDVI and season.
7. **Store results** in `silver.vegetation_health` with deduplication (same buffer + date
   + satellite combination is never processed twice).

### NDVI on the Map

The frontend renders NDVI data as a **heatmap overlay** using Leaflet's heat plugin. Each
buffer's centroid is a heat point with intensity based on NDVI values. The gradient runs
from red (bare/unhealthy) through yellow (degraded) to green (healthy).

---

## Data Pipeline (ETL)

The ETL (Extract, Transform, Load) pipeline follows a **medallion architecture** — data
flows through three layers of increasing refinement.

### Medallion Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  BRONZE (Raw)         SILVER (Processed)      GOLD (Analytics)  │
│  ─────────────        ──────────────────      ────────────────  │
│                                                                 │
│  streams ──────────►  riparian_buffers ─┐                       │
│  waterbodies          (30.48m buffers)  │                       │
│  sinks                                  ├──► riparian_summary   │
│  watersheds           parcel_compliance │    (compliance stats) │
│  parcels ──────────►  (focus area flags) ┘                       │
│                                                                 │
│                       vegetation_health                         │
│                       (NDVI scores)                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Layer | Schema | Purpose | Write Policy |
|-------|--------|---------|--------------|
| **Bronze** | `bronze` | Raw data from external APIs, minimal transformation | Append or upsert |
| **Silver** | `silver` | Spatial analysis results — buffers, compliance, NDVI | Derived from bronze |
| **Gold** | `gold` | Aggregated statistics for dashboards | Derived from silver |
| **Meta** | `meta` | ETL run tracking and audit trail | Internal bookkeeping |

Data flows one direction: **bronze → silver → gold**. Never write back upstream.

### Data Sources

| Source | API | What It Provides |
|--------|-----|------------------|
| **NHDPlus V2.1** | ArcGIS REST (USGS) | Stream centerlines, waterbodies, sinks |
| **Colorado Public Parcels** | ArcGIS REST (CO GIS) | Property boundaries, ownership, land use |
| **USDA Watersheds** | ArcGIS REST (USDA Forest Service) | HUC8 watershed boundary |
| **Sentinel-2 L2A** | STAC API (Planetary Computer) | Satellite imagery for NDVI |

### Pipeline Steps (Full Run)

```
1. load_watershed()          Fetch HUC8 boundary        → bronze.watersheds
2. load_nhdplus_layers()     Fetch streams, waterbodies  → bronze.streams, waterbodies, sinks
3. load_parcels()            Fetch parcels (paginated)   → bronze.parcels
4. generate_buffers()        ST_Buffer on streams        → silver.riparian_buffers
5. analyze_compliance()      ST_Intersects check         → silver.parcel_compliance
6. calculate_summary()       CTE aggregation             → gold.riparian_summary
```

### Design Decisions

**Why Protocol-based DI?** The Python ETL uses `Protocol` classes (PEP 544) to define
interfaces for the feature client (`FeatureClient`) and database writer (`SpatialWriter`).
This allows swapping implementations for testing without changing the pipeline logic.

**Why a staging table for upserts?** GeoPandas `to_postgis()` doesn't support SQL
`ON CONFLICT` clauses. The upsert method writes data to a temporary staging table first,
then uses `INSERT INTO target SELECT FROM staging ON CONFLICT ... DO UPDATE` to merge it
into the real table. The staging table is dropped after each upsert.

**Why the `xmax = 0` trick?** When PostgreSQL executes an `INSERT ... ON CONFLICT DO UPDATE`,
it returns the affected rows but doesn't tell you which were inserts vs. updates. The
system column `xmax` is 0 for newly inserted rows and non-zero for updated rows. By
including `RETURNING (xmax = 0) AS inserted` in the query, the pipeline can count
exactly how many rows were inserted vs. updated.

---

## Incremental Updates

The system supports **incremental updates** so you don't have to reload everything from
scratch each time.

### How It Works

```
Full Run:           Truncate all tables → reload everything from APIs → recompute all

Incremental Run:    Fetch from APIs → upsert (merge) into bronze
                    → Only recompute silver if bronze changed
                    → Only recompute gold if silver changed
```

The incremental pipeline makes smart decisions about what to recompute:

| If This Changed... | Then Recompute... | Reason |
|---------------------|-------------------|--------|
| Streams | Buffers, compliance, summary | Buffer shapes depend on stream geometry |
| Parcels (only) | Compliance, summary | New/moved parcels may overlap buffers |
| Nothing | Skip silver and gold entirely | Data is already current |

### Run Tracking

Every ETL run is logged in `meta.etl_runs` with:
- Run type (full, incremental, ndvi, all)
- Start/end timestamps
- Status (running, completed, failed)
- Row counts (inserted, updated, skipped)
- Change flags (streams/parcels/buffers changed)
- Error message (if failed)

### Triggering Updates

**Manual (CLI):**
```bash
./dev.sh --update                 # Incremental + NDVI (default: "all")
./dev.sh --update incremental     # Bronze upsert + smart silver/gold recompute
./dev.sh --update ndvi            # NDVI refresh only
./dev.sh --update full            # Full reload from scratch
```

**Scheduled (via Aspire):**

Set environment variables in your Aspire configuration:

```
ETL_MODE=scheduled
ETL_SCHEDULE_CRON=0 2 * * *          # Run at 2 AM daily
ETL_UPDATE_TYPE=incremental           # What kind of update to run
```

Or use an interval instead of cron:

```
ETL_MODE=scheduled
ETL_SCHEDULE_INTERVAL_HOURS=24        # Run every 24 hours
ETL_UPDATE_TYPE=all                   # Incremental + NDVI
```

---

## Tech Stack

### Backend (.NET)
| Technology | Version | Purpose |
|-----------|---------|---------|
| **.NET** | 10.0 | Runtime for API and Aspire |
| **ASP.NET Core** | 10.0 | REST API framework (minimal APIs) |
| **.NET Aspire** | 13.1.0 | Service orchestration, health checks, OpenTelemetry |
| **Npgsql** | via Aspire | .NET data provider for PostgreSQL (NpgsqlDataSource) |
| **Dapper** | 2.1 | Micro-ORM for typed and dynamic SQL queries |
| **NetTopologySuite (NTS)** | 4.0.0 | Spatial data types + GeoJSON serialization |
| **OpenTelemetry** | via Aspire | Distributed tracing, metrics, and structured logging |

### Database
| Technology | Version | Purpose |
|-----------|---------|---------|
| **PostgreSQL** | 16 | Relational database |
| **PostGIS** | 3.4 | Spatial extension (geometry types, spatial functions, GiST indexes) |

### ETL Pipeline
| Technology | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12 | ETL runtime |
| **GeoPandas** | >= 1.0 | Spatial DataFrames, read/write PostGIS |
| **SQLAlchemy** | >= 2.0 | Database engine and parameterized SQL |
| **Rasterio** | >= 1.3 | Satellite imagery (COG) reading and clipping |
| **pystac-client** | >= 0.8 | STAC API client for Planetary Computer |
| **APScheduler** | >= 3.10 | Cron/interval job scheduling |
| **GDAL/GEOS/PROJ** | System | Geospatial C libraries (installed in Docker) |

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| **React** | 18.3 | UI framework |
| **TypeScript** | 5.7 | Type-safe JavaScript |
| **Leaflet** | 1.9 | Interactive map rendering |
| **react-leaflet** | 4.2 | React bindings for Leaflet |
| **leaflet.heat** | 0.2 | NDVI heatmap overlay |
| **Tailwind CSS** | 3.4 | Utility-first styling |
| **Vite** | 6.0 | Dev server and build tool |

---

## Project Structure

```
riparian-poc/
├── RiparianPoc.AppHost/               # .NET Aspire orchestrator
│   ├── Program.cs                     #   Service definitions + env var config
│   └── RiparianPoc.AppHost.csproj
│
├── RiparianPoc.Api/                   # C# REST API
│   ├── Endpoints/
│   │   └── GeoDataEndpoints.cs        #   Thin route handlers + DTO records
│   ├── Services/
│   │   ├── IGeoDataServices.cs        #   ISpatialQueryService + IComplianceDataService
│   │   └── GeoDataServices.cs         #   SQL queries + business logic
│   ├── Repositories/
│   │   ├── IPostGisRepository.cs      #   Data access abstraction
│   │   └── PostGisRepository.cs       #   Dapper queries + GeoJSON deserialization
│   ├── Middleware/
│   │   ├── CorrelationMiddleware.cs    #   X-Correlation-Id + X-Session-Id tracking
│   │   └── ExceptionHandlingMiddleware.cs  # Global error → structured JSON
│   ├── Models/
│   │   └── ApiErrorResponse.cs        #   Structured error response record
│   ├── Program.cs                     #   DI registration, middleware pipeline, OTEL setup
│   └── RiparianPoc.Api.csproj
│
├── RiparianPoc.ServiceDefaults/       # Shared Aspire config
│   └── RiparianPoc.ServiceDefaults.csproj  # OpenTelemetry, resilience, service discovery
│
├── python-etl/                        # Python geospatial ETL
│   ├── etl_pipeline.py                #   Main pipeline: fetch → transform → load → analyze
│   ├── ndvi_processor.py              #   Sentinel-2 NDVI calculation + health scoring
│   ├── run_tracker.py                 #   ETL run metadata tracking
│   ├── entrypoint.py                  #   Multi-mode dispatcher (full/incremental/ndvi/scheduled)
│   ├── scheduler.py                   #   APScheduler cron/interval wrapper
│   ├── requirements.txt               #   Python dependencies
│   └── Dockerfile                     #   Python 3.12 + GDAL/GEOS/PROJ
│
├── frontend/                          # React + Leaflet map UI
│   ├── src/
│   │   ├── App.tsx                    #   Main component: map, layers, popups, legend
│   │   ├── main.tsx                   #   React DOM entry point
│   │   ├── index.css                  #   Tailwind directives
│   │   └── components/
│   │       └── NDVILayer.tsx           #   NDVI heatmap overlay component
│   ├── vite.config.ts                 #   Dev server config + API proxy
│   ├── tailwind.config.js
│   ├── nginx.conf                     #   Production SPA routing
│   ├── Dockerfile                     #   Multi-stage: Node build → nginx serve
│   └── package.json
│
├── sql/
│   ├── create_schemas.sql             #   Database schema (source of truth)
│   └── incremental_migration.sql      #   meta.etl_runs + unique constraints
│
├── dev.sh                             #   All-in-one dev script
├── docker-compose.sonar.yml            #   SonarQube server (docker compose)
├── sonar-project.properties            #   SonarQube scanner config
├── azure.yaml                         #   Azure Developer CLI config
├── CLAUDE.md                          #   AI assistant instructions
└── RiparianPoc.sln                    #   .NET solution file
```

---

## Getting Started

### Prerequisites

- **macOS** (project runs from an external drive)
- **Docker Desktop** — configured to store data on the external drive
- **.NET 10 SDK** — `dotnet --version` should show 10.x
- **Node.js 20+** — `node --version` should show 20.x or higher
- **External drive** mounted at `/Volumes/Mac OS Extended 1/`

### Quick Start

```bash
# 1. Navigate to the project
cd "/Volumes/Mac OS Extended 1/riparian-poc"

# 2. Start everything (builds, starts PostGIS, API, frontend, applies schema)
./dev.sh

# 3. In a new terminal, check status
./dev.sh --status

# 4. If data is empty (first run), the ETL runs automatically via Aspire.
#    For manual data refresh:
./dev.sh --update
```

### What `./dev.sh` Does

1. **Pre-flight checks** — verifies the external drive is mounted, Docker is running,
   .NET SDK and Node.js are installed.
2. **Installs frontend dependencies** — runs `npm install` in `frontend/` if
   `node_modules/` doesn't exist.
3. **Builds the .NET solution** — compiles the API, AppHost, and ServiceDefaults projects.
4. **Starts Aspire** — launches the AppHost which starts PostGIS, the API, the ETL
   container, and the frontend dev server.
5. **Waits for PostGIS** — polls the database for up to 90 seconds until it's ready.
6. **Applies the schema** — runs `create_schemas.sql` if the `bronze.streams` table
   doesn't exist yet.

### Accessing the Application

| Service | URL |
|---------|-----|
| **Frontend (map)** | http://localhost:3000 |
| **Aspire Dashboard** | http://localhost:18888 |
| **API** | http://localhost:8000 |

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `./dev.sh` | Start all services |
| `./dev.sh --status` | Check health of all services + data counts |
| `./dev.sh --stop` | Stop Aspire (PostGIS container persists with data) |
| `./dev.sh --restart` | Stop and restart all services |
| `./dev.sh --update` | Run incremental + NDVI update (alias for `--update all`) |
| `./dev.sh --update incremental` | Upsert bronze data, smart-recompute silver/gold |
| `./dev.sh --update ndvi` | Refresh NDVI vegetation health only |
| `./dev.sh --update full` | Full reload from scratch |
| `./dev.sh --sonar` | Start SonarQube server (http://localhost:9000) |
| `./dev.sh --sonar-stop` | Stop SonarQube (data persists in Docker volumes) |
| `./dev.sh --lint` | Run static analysis: Python + TypeScript + SQL |
| `./dev.sh --lint-dotnet` | Run static analysis: C# .NET projects |
| `./dev.sh --help` | Show usage help |

### Build Commands

```bash
dotnet build RiparianPoc.sln          # Build all .NET projects
cd frontend && npm run dev            # Frontend dev server (standalone)
cd frontend && npm run build          # Frontend production build
cd python-etl && python entrypoint.py # Run ETL directly (needs DATABASE_URL)
```

### Database Commands

```bash
# Check status (includes row counts)
./dev.sh --status

# Connect to the database manually (find container ID first)
docker exec -it <container_id> bash -c 'PGPASSWORD=$POSTGRES_PASSWORD psql -U postgres -d ripariandb'

# Example queries once connected:
SELECT count(*) FROM bronze.streams;
SELECT count(*) FROM silver.parcel_compliance WHERE is_focus_area = TRUE;
SELECT * FROM gold.riparian_summary;
SELECT * FROM meta.etl_runs ORDER BY started_at DESC;
```

---

## API Endpoints

All endpoints return **GeoJSON FeatureCollections** (except vegetation and summary which
return typed JSON arrays). On error, all endpoints return a structured
`ApiErrorResponse` JSON body (see [Observability](#observability)).

### GET /api/streams
Returns all stream centerlines from the bronze layer.

**Response properties:** `comid`, `gnis_name`, `reach_code`, `ftype`, `fcode`,
`stream_order`, `length_km`

### GET /api/buffers
Returns riparian buffer polygons from the silver layer, joined with stream names.

**Response properties:** `stream_id`, `buffer_distance_m`, `area_sq_m`, `stream_name`

### GET /api/parcels
Returns all parcels with their compliance status (left-joined with compliance data).

**Response properties:** `parcel_id`, `land_use_desc`, `land_use_code`, `zoning_desc`,
`owner_name`, `land_acres`, `is_focus_area`, `overlap_pct`, `focus_area_reason`

### GET /api/focus-areas
Returns only parcels identified as focus areas.

**Response properties:** Same as parcels, but only where `is_focus_area = TRUE`.

### GET /api/vegetation/buffers/{bufferId}
Returns NDVI time series for a specific buffer zone.

**Response fields:** `buffer_id`, `acquisition_date`, `mean_ndvi`, `min_ndvi`,
`max_ndvi`, `health_category`, `season_context`, `satellite`, `processed_at`

### GET /api/summary
Returns watershed-level compliance summary from the gold layer.

**Response fields:** `huc8`, `total_stream_length_m`, `total_buffer_area_sq_m`,
`total_parcels`, `compliant_parcels`, `focus_area_parcels`, `compliance_pct`,
`avg_ndvi`, `healthy_buffer_pct`, `degraded_buffer_pct`, `bare_buffer_pct`

---

## Database Schema

### Bronze Layer (Raw Data)

| Table | Source | Key Column | Geometry |
|-------|--------|------------|----------|
| `bronze.streams` | NHDPlus V2.1 | `comid` (UNIQUE) | LineString |
| `bronze.waterbodies` | NHDPlus V2.1 | `comid` | Polygon |
| `bronze.sinks` | NHDPlus V2.1 | `comid` | Point |
| `bronze.parcels` | Colorado Parcels | `parcel_id` (UNIQUE) | MultiPolygon |
| `bronze.watersheds` | USDA Watersheds | `huc8` | MultiPolygon |

### Silver Layer (Processed)

| Table | Derived From | Key Relationships |
|-------|-------------|-------------------|
| `silver.riparian_buffers` | bronze.streams | `stream_id` → streams.id |
| `silver.parcel_compliance` | parcels + buffers | `parcel_id` → parcels.id, `buffer_id` → buffers.id |
| `silver.vegetation_health` | Sentinel-2 imagery | `buffer_id` → buffers.id, UNIQUE(buffer_id, acquisition_date, satellite) |

### Gold Layer (Analytics)

| Table | Aggregation Level |
|-------|-------------------|
| `gold.riparian_summary` | Per watershed (HUC8) |

### Meta Layer (Operations)

| Table | Purpose |
|-------|---------|
| `meta.etl_runs` | Tracks every ETL execution with status, counts, and timing |

### Coordinate Reference System

All geometry is stored in **EPSG:4269 (NAD83)** — coordinates are in degrees of latitude
and longitude. For distance and area calculations, geometry is cast to the `geography`
type, which computes on Earth's curved surface in meters.

### Indexes

Every geometry column has a **GiST index** for fast spatial queries. Additional B-tree
indexes exist on foreign keys and frequently queried columns. A **partial index** on
`is_focus_area = TRUE` speeds up focus-area queries.

---

## Code Quality (SonarQube)

The project uses **SonarQube Community Edition** for local static code analysis. The
server runs as a Docker container via `docker-compose.sonar.yml`, and scanners run
as one-shot Docker containers or CLI tools.

### What SonarQube Analyzes

| Language | Scanner | What It Catches |
|----------|---------|-----------------|
| **Python** | Generic scanner (`sonar-scanner-cli`) | Bugs, code smells, security hotspots, complexity, duplication |
| **TypeScript** | Generic scanner (`sonar-scanner-cli`) | Bugs, code smells, security vulnerabilities, unused imports |
| **SQL** | Generic scanner (`sonar-scanner-cli`) | Code smells in SQL files |
| **C#** | .NET scanner (`dotnet-sonarscanner`) | All of the above plus Roslyn-based semantic analysis |

### Quick Start

```bash
# 1. Start the SonarQube server (first run pulls the image + initializes, ~60s)
./dev.sh --sonar

# 2. Set up authentication (required before scanning):
#    a. Open http://localhost:9000, log in with admin / admin
#    b. Change your password when prompted
#    c. Go to My Account > Security > Generate Token
#    d. Export the token:
export SONAR_TOKEN="sqp_your-token-here"

# 3. Run analysis on Python + TypeScript + SQL
./dev.sh --lint

# 4. (Optional) Run analysis on C# .NET code
./dev.sh --lint-dotnet

# 5. View results
open http://localhost:9000/dashboard?id=riparian-poc
```

### Commands

| Command | Description |
|---------|-------------|
| `./dev.sh --sonar` | Start SonarQube via docker compose (http://localhost:9000) |
| `./dev.sh --sonar-stop` | Stop SonarQube via docker compose (data persists) |
| `./dev.sh --lint` | Analyze Python, TypeScript, and SQL (requires `SONAR_TOKEN`) |
| `./dev.sh --lint-dotnet` | Analyze C# .NET projects (requires `SONAR_TOKEN`, auto-installs `dotnet-sonarscanner`) |

### How It Works

The SonarQube server is defined in `docker-compose.sonar.yml` with:
- `SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true` (avoids needing `vm.max_map_count` on macOS)
- Health check that polls `/api/system/status` until the server reports `UP`
- Named Docker volumes for persistent data, logs, and extensions

**Python + TypeScript scanning** runs the `sonarsource/sonar-scanner-cli` Docker image.
The scanner reads `sonar-project.properties`, scans `python-etl/`, `frontend/src/`, and
`sql/`, then uploads results to SonarQube. On macOS, it reaches the server via
`host.docker.internal:9000` (since `--network host` doesn't work on Docker Desktop).

**C# scanning** uses `dotnet-sonarscanner` (a .NET global tool) which wraps the
`dotnet build` process. It instruments the MSBuild pipeline to extract Roslyn diagnostics
and sends them to SonarQube. This runs directly on the host, so it connects to
`localhost:9000`.

### Authentication

SonarQube requires **token-based authentication** (username/password auth is deprecated
in SonarQube 10+). After first login:

1. Open http://localhost:9000
2. Log in with **admin / admin**, change your password when prompted
3. Go to **My Account > Security > Generate Token**
4. Export the token before running scans:
   ```bash
   export SONAR_TOKEN="sqp_your-token-here"
   ```
   Or persist it in `.env` (already in `.gitignore`):
   ```bash
   echo 'SONAR_TOKEN=sqp_your-token-here' >> .env
   ```

### Data Persistence

SonarQube data is stored in Docker volumes (`sonarqube-data`, `sonarqube-logs`,
`sonarqube-extensions`). Running `./dev.sh --sonar-stop` preserves all project history,
quality profiles, and analysis results. To fully reset, remove the volumes:
```bash
docker compose -f docker-compose.sonar.yml down -v
```

---

## Azure Deployment

The project includes Azure deployment configuration via the Azure Developer CLI (`azd`).

```bash
azd init           # First-time setup
azd up             # Deploy all services
azd deploy         # Redeploy after changes
azd deploy --service api   # Redeploy a single service
azd down           # Tear down all resources
```

The frontend Dockerfile uses a multi-stage build: Node.js builds the Vite app, then
nginx serves the static files with SPA routing support.

---

## Troubleshooting

### "External drive not mounted"
Mount the drive at `/Volumes/Mac OS Extended 1/` before running any commands.

### Aspire dashboard won't start (HTTPS error)
The dev script uses HTTP-only mode (`ASPIRE_ALLOW_UNSECURED_TRANSPORT=true`). If you see
HTTPS certificate errors, ensure `dev.sh` is setting this environment variable.

### ETL container exits with code 1
Check the container logs in the Aspire dashboard. Common causes:
- **Connection string format:** Aspire injects ADO.NET format; the ETL converts it to
  PostgreSQL URI format automatically.
- **Schema not applied:** The ETL expects tables to exist. Run `./dev.sh` (which applies
  the schema) before running `./dev.sh --update`.

### Empty map (no layers displayed)
Run `./dev.sh --status` to check data counts. If streams/parcels/buffers show 0, the ETL
hasn't run yet or failed. Check the ETL container logs in the Aspire dashboard.

### "ON CONFLICT" duplicate key errors
The Colorado Parcels API sometimes returns duplicate `parcel_id` values within a single
batch. The upsert method handles this by deduplicating the staging table before merging.

### PostGIS container keeps restarting
Check Docker Desktop's disk space. PostGIS data is stored in Docker volumes on the
external drive at `/Volumes/Mac OS Extended 1/DockerData/`.

---

## Observability

The API includes built-in distributed tracing, structured logging, and error handling
powered by **OpenTelemetry** and **.NET Aspire**.

### Correlation & Session Tracking

Every API request is tagged with two identifiers:

- **Correlation ID** (`X-Correlation-Id` header) — ties a single HTTP request to all
  its downstream database queries and log entries. Derived from the W3C TraceId.
- **Session ID** (`X-Session-Id` header) — ties multiple API calls together for a
  single user session. Generated by the frontend on page load.

The frontend sends `X-Session-Id` with every request. The middleware extracts both IDs,
attaches them to the OpenTelemetry trace as tags, and wraps all downstream logging in a
scope so every log entry includes `CorrelationId`, `SessionId`, and `ClientIp`.

### Distributed Tracing

Three custom `ActivitySource` instances create nested trace spans:

```
HTTP GET /api/streams (ASP.NET Core auto-span)
  └── SpatialQuery.GetStreams (service span)
       └── PostGis.QueryGeoJson (repository span)
            └── Npgsql query (auto-instrumented)
```

In the Aspire Dashboard (http://localhost:18888):
- **Traces** tab — view the full span hierarchy for each request
- Filter by `session.id` tag to see all API calls for one user session
- Filter by `correlation.id` to drill into a single request

### Error Handling

Errors are handled in layers (defense in depth):

| Layer | Responsibility |
|-------|---------------|
| **Repository** | Catches `NpgsqlException`, enriches trace with timing, wraps with context |
| **Service** | Validates input (e.g., `bufferId <= 0` → `ArgumentException`) |
| **ExceptionHandlingMiddleware** | Maps exception types to HTTP status codes, returns structured JSON |

Error responses use a consistent JSON format:

```json
{
  "error": "Buffer ID must be positive, got -1",
  "correlationId": "a1b2c3d4e5f6...",
  "statusCode": 400,
  "detail": "System.ArgumentException: ..."
}
```

The `detail` field is only populated in the Development environment. Exception type
mapping:

| Exception | HTTP Status | Message Policy |
|-----------|-------------|----------------|
| `NpgsqlException` | 503 | Generic ("Database temporarily unavailable") |
| `ArgumentException` | 400 | Exception message exposed (user-facing) |
| `KeyNotFoundException` | 404 | Exception message exposed |
| `OperationCanceledException` | 504 | Generic ("Request timed out") |
| Other | 500 | Generic ("An unexpected error occurred") |

### API Architecture

The API follows a layered architecture with interface segregation:

```
Endpoints (thin handlers)
    ↓ inject
Services (ISpatialQueryService, IComplianceDataService)
    ↓ inject
Repository (IPostGisRepository)
    ↓ uses
NpgsqlDataSource + Dapper
```

- **Endpoints** — route handlers only, no SQL or business logic
- **Services** — own SQL queries, input validation, ActivitySource tracing
- **Repository** — generic data access (GeoJSON and typed queries via Dapper)
- All registered as scoped services in DI
