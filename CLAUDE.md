# San Juan Riparian Watch

## Project Overview
A basin-scale **riparian vegetation delineation + health + change-monitoring** platform for
the San Juan River watershed. Learns *where riparian vegetation actually is* from satellite
time series (replacing fixed hydrology buffers), scores its condition (incl. tamarisk /
Russian-olive invasive cover), and detects change over the long EO record. Stack: STAC
Earth-observation ETL (Sentinel-2/1, Landsat, land cover, 3DEP DEM via Microsoft Planetary
Computer) + PostgreSQL/PostGIS + Python ML (`riparian/` package: RF baseline vs. OlmoEarth
foundation model) + .NET Aspire-orchestrated C# REST API + React/MapLibre map frontend.

> **3-stage pipeline:** delineate riparian extent (Stage 1, built + validated vs NMRipMap) →
> score condition + invasives (Stage 2) → detect annual change / invasive spread (Stage 3).
> See `docs/STATUS.md` for current state, `docs/specs/` for the specs, `docs/decisions/` for
> ADRs. Some legacy buffer-centric tables/modules remain from the original POC.

## AI Workflow (Encoding Loop)
This repo uses the NextAurora **encoding-loop method**: rules encoded across 5 surfaces
(this file + `.claude/`, `.coderabbit.yaml`, the `architecture-reviewer` agent, commands +
skills, `docs/` + diagrams) × 3 enforcement tiers, kept from drifting by mechanical hooks.
- **Shared vocabulary:** `CONTEXT.md` (riparian science + method terms)
- **Procedures:** `/feature-spec`, `/check-rules`, `/sync-status`, `/add-endpoint`,
  `/add-etl-step`, `/add-map-layer` in `.claude/commands/`
- **Lean canon:** keep this file under **500 lines** (soft 400). Detail beyond a
  one-paragraph headline moves to a paired `docs/` doc; the paraphrase ends with
  `See CLAUDE.md` so the `check-claude-md-refs.sh` hook can find it.
- **File-move discipline:** `git mv`/`git rm` triggers a stale-reference audit.

## External Drive Configuration
**IMPORTANT**: This entire project lives on an external drive. The drive MUST be mounted
before starting Docker, running any services, or editing code.

Disk layout:
- `EXTERNAL DRIVE: /Volumes/Mac OS Extended 1/`
  - `Riparian_Buffer_POC/` — this repo (source + solution)
  - `DockerData/DockerDesktop/` — Docker images + volumes (~15GB+), incl. persistent postgis

Pre-flight — verify the drive is mounted before running anything:
```
ls "/Volumes/Mac OS Extended 1/Riparian_Buffer_POC"
ls "/Volumes/Mac OS Extended 1/DockerData"
```
If either fails, the external drive is not mounted. Mount it before proceeding.

### Service Architecture
| Service              | Container Name      | Port  |
|----------------------|---------------------|-------|
| PostgreSQL + PostGIS | riparian_postgis    | 5432  |
| C# REST API          | riparian_api        | 8000  |
| React Frontend       | riparian_frontend   | 80    |
| Python ETL           | riparian_etl        | —     |

Access URLs (local dev): Frontend http://localhost · API http://localhost:8000 · Swagger
http://localhost:8000/swagger · Aspire Dashboard http://localhost:18888

## Commands

### Quick Start (Recommended)
```
./dev.sh              # Start everything (checks drive I/O, starts PostGIS + Aspire)
./dev.sh --status     # Check service health + drive I/O + data counts (incl. NDVI)
./dev.sh --restart    # Restart all services
./dev.sh --stop       # Stop everything gracefully
./dev.sh --reconnect  # Recover after external drive disconnect/reconnect
./dev.sh --backup     # Snapshot database to backups/ (timestamped pg_dump)
./dev.sh --restore    # Restore from latest backup (prompts for confirmation)
```
Always use `./dev.sh` instead of running services manually.

**WARNING**: Never kill Aspire processes directly (`kill`, `pkill`, Activity Monitor). This
can restart the PostgreSQL container and corrupt data. Always use `./dev.sh --stop`.

Drive disconnect recovery: reconnect + wait for mount → `./dev.sh --reconnect` → `./dev.sh`
→ if data was lost, `./dev.sh --restore` (auto-backups are taken before full ETL runs).

### Build & Run
- Start everything: `./dev.sh` · via Aspire directly: `dotnet run --project RiparianPoc.AppHost`
- Build solution: `dotnet build RiparianPoc.sln` · API only: `dotnet run --project RiparianPoc.Api`
- Run ETL: `cd python-etl && python etl_pipeline.py`
- Frontend dev (hot-reload): `cd frontend && npm run dev` (:3000) · build: `npm run build`

### Testing
- **Python unit tests**: `cd python-etl && pytest` — pure-function suite (`tests/`) covering the
  `riparian/` package: spectral indices + texture, temporal stats, grid/`spatial_dims`, weak-label
  `near_water_mask`, `is_invasive`, validation metrics (`compare_masks`, `assign_spatial_folds`).
  Tests marked `@pytest.mark.live` hit real STAC/DB — skipped in CI, run manually.
- **C# unit tests**: `dotnet test RiparianPoc.Api.Tests` — xUnit + NSubstitute over the service
  layer (spatial + compliance: input validation, repository delegation, GeoJSON/MVT query shape)
  with `IPostGisRepository` mocked, plus `MvtTileSql` tile-SQL invariants. No live-DB integration
  test yet. **Frontend**: no test runner yet — `npm run lint` (tsc) only.
- Lint C#: `dotnet format` · Lint frontend: `cd frontend && npm run lint`

### Code Quality
SonarQube (static analysis: Python/TS/SQL/C#) is the **Tier-3** gate; CodeRabbit
(`.coderabbit.yaml` path rules) is the **Tier-2** AI-review surface that carries these
conventions. Quick: `./dev.sh --sonar` (start server), `./dev.sh --lint` (scan py/ts/sql),
`./dev.sh --lint-dotnet` (scan C#). Full setup, commands, and replication guide:
**docs/sonarqube.md**. When asking for a quality check, say "run SonarQube" — not Codacy.

### Database
- **Persistence**: PostgreSQL data is bind-mounted to `./pgdata/` (`.WithDataBindMount("../pgdata")`
  in AppHost) — survives the frequent Docker restarts on the external drive. `pgdata/` is gitignored.
- **Backup/restore**: `./dev.sh --backup` (→ `backups/ripariandb_*.dump`, keeps latest 5, `pg_dump -Fc`),
  `./dev.sh --restore` (drops + recreates from latest). Always back up after a successful full ETL.
- **Manual access**: Aspire auto-generates the password.
  `PGPASSWORD=$(docker exec <pg-container> printenv POSTGRES_PASSWORD) psql -h localhost -p <port> -U postgres -d ripariandb`
- **Schema reset**: apply `sql/create_schemas.sql` then `sql/incremental_migration.sql`.

### Azure Deployment
`azd init` then `azd up` (first time) · `azd deploy` (redeploy) · `azd deploy --service api`
(single) · `azd down` (tear down).

### ETL Operations
```
./dev.sh --update              # Incremental ETL (default, preserves NDVI data)
./dev.sh --update full         # Full reload (auto-backs up NDVI first, warns before deleting)
./dev.sh --update ndvi         # NDVI processing only
```
- **Default ETL mode is `incremental`** (not `full`) — Aspire restarts won't wipe NDVI data
- `./dev.sh --update full` auto-backs up before truncating if NDVI readings exist
- Full ETL truncates buffers which deletes vegetation_health (FK dependency, no CASCADE)
- NDVI `process_buffers_incremental()` defaults to current year's growing season (June–August)
- In winter months, use `process_buffers('YYYY-06-01/YYYY-08-31')` with an explicit past range

## Architecture

### Solution Structure
```
riparian-poc/
├── RiparianPoc.AppHost/          # .NET Aspire orchestrator (entry point)
├── RiparianPoc.Api/              # C# ASP.NET Core REST API (minimal APIs)
│   ├── Endpoints/GeoDataEndpoints.cs      # Thin route handlers + DTO records
│   ├── Services/IGeoDataServices.cs       # ISpatialQueryService + IComplianceDataService
│   ├── Services/GeoDataServices.cs        # service impls (SQL + business logic)
│   ├── Repositories/IPostGisRepository.cs # data access abstraction
│   ├── Repositories/PostGisRepository.cs  # Dapper + NpgsqlDataSource + GeoJSON
│   ├── Middleware/CorrelationMiddleware.cs, ExceptionHandlingMiddleware.cs
│   └── Models/ApiErrorResponse.cs
├── RiparianPoc.ServiceDefaults/  # Shared Aspire service configuration
├── python-etl/                   # Python geospatial ETL pipeline
│   ├── riparian/                 # riparian AI package (domain-organized)
│   │   ├── datacube/             #   stac.py, features.py — STAC access + feature engineering
│   │   ├── delineation/          #   hand, weak_labels, baseline, validate, olmoearth, runner (Stage 1)
│   │   ├── health/               #   invasive.py (+ condition scoring, Stage 2)
│   │   ├── reaches/              #   processor.py — per-reach network product
│   │   └── validation/           #   reference.py — NMRipMap/CO-RIP validation
│   ├── etl_pipeline.py           # Legacy orchestrated pipeline (scene-first ingest)
│   ├── ndvi_processor.py, nlcd_processor.py, landfire_processor.py, ssurgo_processor.py,
│   │   lidar_processor.py, raster_processor.py  # legacy source ingest (flat, still wired to entrypoint)
│   ├── health_scorer.py          # SMP 80/10/10 composite health scoring model
│   ├── run_tracker.py, entrypoint.py, scheduler.py, requirements.txt, Dockerfile
├── frontend/                     # React 18 + Leaflet + Tailwind (src/App.tsx, components/)
├── sql/                          # create_schemas.sql (source of truth) + *_migration.sql
├── docs/                         # STATUS.md, sonarqube.md, specs/, decisions/ (+ diagrams)
├── .claude/                      # agents/, commands/, skills/, scripts/ (encoding-loop tooling)
├── CONTEXT.md, azure.yaml, RiparianPoc.sln
```

### Medallion Architecture
- **bronze**: Raw ingested data, minimal transformation. Tables: streams, waterbodies, sinks,
  parcels, watersheds, nwi_wetlands, ssurgo_soils, riparian_training_samples.
- **silver**: Spatial processing — buffer generation, parcel compliance, wetland/soil/raster
  intersections, canopy height, NDVI health, riparian_extent. Tables: riparian_buffers,
  parcel_compliance, vegetation_health, buffer_wetlands, buffer_soils, buffer_land_cover,
  buffer_vegetation_structure, buffer_canopy, riparian_extent.
- **gold**: Aggregated analytics. Tables: riparian_summary, buffer_health_score.

Data flows one direction: bronze → silver → gold. **Never write back upstream.**

### Services and How They Connect
- **Aspire AppHost** orchestrates all services with automatic service discovery
- **PostgreSQL + PostGIS** is the shared data store (connection strings injected by Aspire)
- **C# API** reads from all three schemas, returns GeoJSON via NetTopologySuite (18 endpoints)
- **Python ETL** writes to bronze, silver, and gold (concurrent bronze + silver processing)
- **React frontend** calls the C# API, renders on Leaflet map with timelapse slider
- External data (Python ETL, all free / no API key): **Microsoft Planetary Computer** (Sentinel-2,
  Sentinel-1, 3DEP LiDAR — a STAC API), **FWS NWI MapServer** (wetlands), **NRCS Soil Data
  Access** (SSURGO soils + hydric ratings), **LANDFIRE LF250 ImageServer** (EVT/EVH), **MRLC
  NLCD ImageServer** (land cover).

### API Endpoints (18 total)
- `GET /api/streams` — stream centerlines from bronze (GeoJSON)
- `GET /api/buffers` — riparian buffer polygons from silver (GeoJSON)
- `GET /api/buffers/health` — buffers with latest NDVI health (LEFT JOIN LATERAL to vegetation_health)
- `GET /api/buffers/health/{date}` — buffers with NDVI health for a specific date
- `GET /api/buffers/scores` — buffers with SMP composite health scores (A–F grades)
- `GET /api/parcels` — parcels with compliance status · `GET /api/focus-areas` — focus parcels only
- `GET /api/wetlands` — NWI wetlands (bronze) · `GET /api/soils` — SSURGO soils (bronze)
- `GET /api/buffers/{bufferId}/wetlands|landcover|vegetation-structure|soils|canopy` — per-buffer overlaps
- `GET /api/buffers/{bufferId}/score` — detailed SMP health score breakdown (10 sub-scores)
- `GET /api/vegetation/buffers/{bufferId}` — NDVI time series · `GET /api/ndvi/dates` — distinct dates
- `GET /api/summary` — gold layer compliance summary + grade distribution

## Conventions

### Spatial Data
- All geometry uses **EPSG:4269 (NAD83)** as the storage CRS
- Always cast to geography for distance/area: `geom::geography`; `ST_Buffer(geom::geography, meters)`
  — never buffer in degrees
- Distances in meters internally → feet for display (× 3.28084); areas in sq m → acres (/ 4046.86)
- Always use GiST indexes on geometry columns; bounding-box pre-filter (`&&`) before expensive ops

### Field Mapping (API → Database)
Colorado Public Parcels REST fields → columns (renamed in `etl_pipeline.py` `load_parcels()`):
`parcel_id`→`parcel_id`, `landUseDsc`→`land_use_desc`, `landUseCde`→`land_use_code`,
`zoningDesc`→`zoning_desc`, `owner`→`owner_name`, `landAcres`→`land_acres`.

### NDVI & Phenology
- NDVI = (NIR − Red) / (NIR + Red), range −1 to +1
- Health thresholds calibrated for semi-arid San Juan Basin (peak-growing median ~0.17):
  healthy (>0.25), degraded (0.10–0.25), bare (<0.10) — the single source of truth is
  `classify_health()` in `ndvi_processor.py`; keep the frontend legend in sync
- Only use imagery from **peak growing season (June–August)** for the San Juan Basin
- Tag every vegetation_health record with `season_context`; dormant readings score `dormant`, not `bare`

### C# / .NET
Follow SOLID + the prompt-library dotnet standards
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/dotnet).
- **SOLID**: SRP, OCP, LSP, ISP (small focused interfaces), DIP (depend on abstractions)
- ASP.NET Core minimal APIs (top-level Program.cs), .NET 10 features
- `sealed` classes when not designed for inheritance; file-scoped namespaces; `record` DTOs/value objects
- Nullable reference types on, `?` annotations; constructor injection with null guards
  (`?? throw new ArgumentNullException`)
- `ILogger<T>` structured logging with message templates (not string interpolation)
- `CancellationToken` on all async signatures; `async/await` for I/O; avoid `async void`
- `TypedResults` for endpoint returns (compile-time OpenAPI metadata); XML docs on public APIs
- GeoJSON via NetTopologySuite.IO.GeoJSON; connection string name `"ripariandb"` (Aspire-resolved)
- CORS open for dev; lock down for prod. Tests: xUnit, AAA, NSubstitute/Moq. Methods < 20 lines.
  Prefer immutability (records, init-only).

#### Data Access (Dapper)
- **Dapper** micro-ORM with `NpgsqlDataSource` (not EF Core for geo queries)
- `Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true` set in Program.cs
- `QueryAsync(CommandDefinition)` for dynamic GeoJSON rows; `QueryAsync<T>(CommandDefinition)` for typed DTOs
- Always pass `CancellationToken` via `CommandDefinition`
- GeoJSON: `ST_AsGeoJSON(geom) AS geojson` → extract `geojson`, deserialize with
  `NetTopologySuite.IO.Converters.GeoJsonConverterFactory`, build `Feature` with remaining columns
  as `AttributesTable`

#### Service Layer Architecture
- **Endpoints** (`GeoDataEndpoints.cs`): thin route handlers only — no SQL, no business logic.
  Inject a service interface, call one method, return the result.
- **Services** (`GeoDataServices.cs`): own all SQL + business logic. Two ISP interfaces:
  `ISpatialQueryService` (5 GeoJSON methods), `IComplianceDataService` (2 typed methods). Input
  validation here (`ArgumentException` for bad IDs).
- **Repository** (`PostGisRepository.cs`): generic data access — `IPostGisRepository` with
  `QueryGeoJsonAsync` + `QueryAsync<T>`. Connection lifetime, GeoJSON deserialization,
  `NpgsqlException` handling.
- DI: all scoped (`AddScoped<TInterface, TImpl>`) in Program.cs.

#### Observability (OpenTelemetry + Aspire)
- Aspire ServiceDefaults provides base OTEL (tracing, metrics, logging `IncludeScopes=true`, OTLP export)
- Three custom `ActivitySource`s registered additively via `AddOpenTelemetry().WithTracing()`:
  `RiparianPoc.Api.Repository`, `.SpatialQuery`, `.ComplianceData`
- Trace hierarchy: HTTP request → Service span → Repository span → Npgsql auto-span
- Each service/repo method: `using var activity = Source.StartActivity("Name")` + `activity?.SetTag()`
  for result counts and timing

#### Correlation & Session Tracking
- `CorrelationMiddleware` extracts `X-Correlation-Id` (or W3C TraceId) and `X-Session-Id`; sets
  `Activity.Current` tags `correlation.id` / `session.id` / `client.ip`
- `ILogger.BeginScope()` adds `CorrelationId` / `SessionId` / `ClientIp` to downstream logs
- Response includes `X-Correlation-Id`; CORS must `.WithExposedHeaders("X-Correlation-Id")`
- Frontend generates `SESSION_ID = crypto.randomUUID()` per page load, sent on every fetch

#### Error Handling (Defense in Depth)
- `ExceptionHandlingMiddleware` catches all unhandled exceptions globally
- Exception → status: `NpgsqlException`→503, `ArgumentException`→400, `KeyNotFoundException`→404,
  `OperationCanceledException`→504, default→500
- 4xx expose `ex.Message` (user-facing); 5xx use generic messages
- `ApiErrorResponse` record `{ error, correlationId, statusCode, detail? }` — `detail` only in Development
- Repository catches `NpgsqlException`, logs DB context + timing, sets `Activity.SetStatus(Error)`, rethrows

### Python
Follow SOLID + the prompt-library python standards
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/python).
- **SOLID**: `Protocol` classes (PEP 544) for interfaces, constructor injection via `__init__`
- Python 3.11+; PEP 8 (snake_case funcs/vars, PascalCase classes); type hints on ALL params + returns
- `@dataclass(frozen=True)` for data structures; Pydantic for validation
- Google-style docstrings on all public functions/classes; custom exceptions (no bare `except Exception`)
- Context managers (`with`) for all resources; `logging` module (never log sensitive data)
- SQLAlchemy + `text()` for parameterized SQL; GeoPandas for PostGIS I/O
- `planetary_computer.sign_inplace` for STAC; `rasterio.mask.mask()` to clip rasters to geometries
- Tests: pytest, AAA, fixtures, pytest-mock. Functions < 25 lines. Prefer immutable data.

### SQL (PostgreSQL / PostGIS)
Follow the prompt-library sql standards
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/sql).
- snake_case names (tables, columns, indexes e.g. `idx_streams_geom`)
- Always name columns in SELECT — never `SELECT *` in production
- CTEs for complex multi-step queries; parameterized only (never concatenate input); FK constraints
- Audit timestamps (`imported_at`/`created_at`/`processed_at`) on all tables
- `EXISTS` over `IN` for large-dataset subqueries; table aliases in JOINs; comments on complex logic
- Transactions for multi-step writes; NUMERIC for precision; `&&` bbox pre-filter before spatial ops

### Frontend
- React 18 + TypeScript, **MapLibre GL via `react-map-gl/maplibre`**, Vite, Tailwind; API base from `VITE_API_URL`
- Most layers are **MVT vector tiles** (`<Source type="vector" tiles={.../api/tiles/{z}/{x}/{y}.pbf}>` + `<Layer>`); GeoJSON `<Source type="geojson">` for smaller layers (e.g. riparian extent)
- Layer visibility toggled via the `layout.visibility` paint prop; interactivity via `interactiveLayerIds`
- Buffer/riparian styling via MapLibre paint expressions (`match`/`interpolate` on feature props)
- Basemap toggle: street / satellite / NAIP `RasterTileSource`
- Session: `crypto.randomUUID()` per page load → `X-Session-Id` header on every fetch
- `fetchJson<T>` helper sends the session header, logs `X-Correlation-Id`, parses `ApiErrorResponse` on failure

### Code Quality Files
`docker-compose.sonar.yml` (SonarQube server + PG backend), `sonar-project.properties` (scanner
config), `.coderabbit.yaml` (Tier-2 AI-review path rules), `.vscode/settings.json` (connected mode),
`.vscode/extensions.json` (recommended extensions), `.env` (gitignored, `SONAR_TOKEN`).

## Do Not Modify (without explicit request)
- `sql/create_schemas.sql` — schema source of truth (add additive `*_migration.sql` instead)
- `azure.yaml` — Azure deployment config
- `RiparianPoc.AppHost/Program.cs` — Aspire orchestration
- Coordinate reference systems (EPSG:4269 for storage)
- **Do not add NuGet / npm / pip packages without asking**
- Do not reorganize the **.NET Aspire solution** (AppHost references projects by path; `azure.yaml`
  + Dockerfiles are coupled to it) or the established repo layout without asking. Riparian AI
  Python code has a sanctioned home — the `python-etl/riparian/` package (domain subpackages);
  put new delineation/health/reach/validation modules there, not as new flat files.
- Do not change field mappings in `etl_pipeline.py` without updating the schema

## Common Patterns

### Adding a new API endpoint  (`/add-endpoint`)
1. Add the method to the appropriate service interface (`ISpatialQueryService` or
   `IComplianceDataService`) in `Services/IGeoDataServices.cs`
2. Implement in `Services/GeoDataServices.cs` — SQL with `ST_AsGeoJSON(geom) AS geojson`, call
   `_repository.QueryGeoJsonAsync()` or `QueryAsync<T>()`
3. Add `using var activity = Source.StartActivity(...)` + completion logging
4. Add a thin route handler in `Endpoints/GeoDataEndpoints.cs` that injects the service
5. Return `TypedResults.Ok(result)`

### Adding a new ETL step  (`/add-etl-step`)
1. Add a function in `etl_pipeline.py` (or a new `*_processor.py` for a distinct source/model)
2. Use `engine.connect()` + `text()` for SQL, or `gpd.read_postgis()` for reads
3. Call it from `main()` in the correct pipeline order (or wire an `entrypoint.py` `--mode`)
4. Log at start and end of the function

### Adding a new map layer  (`/add-map-layer`)
1. Fetch from API in `App.tsx` useEffect → 2. Add a `<GeoJSON>` component with a style function
→ 3. Add popup via `onEachFeature` → 4. Add to the legend

## Data Sources
- NHDPlus V2.1: https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/NHDPlusV21/FeatureServer
- Colorado Parcels: https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0
- USDA Watersheds: https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_Watersheds_01/MapServer
- Sentinel-2 / Sentinel-1 / 3DEP LiDAR via Planetary Computer (STAC): https://planetarycomputer.microsoft.com/api/stac/v1
- NWI Wetlands: https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0
- SSURGO Soils: https://SDMDataAccess.sc.egov.usda.gov/ (spatial WFS + tabular REST)
- LANDFIRE EVT/EVH LF250: https://lfps.usgs.gov/arcgis/rest/services/Landfire_LF250/
- MRLC NLCD: https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/ows
- Study area: San Juan Basin, HUC8 code 14080101
