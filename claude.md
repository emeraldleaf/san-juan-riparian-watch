```markdown
# Riparian Buffer Compliance POC

## Project Overview
A .NET Aspire-orchestrated proof-of-concept that monitors riparian buffer zone compliance
using PostgreSQL/PostGIS spatial analysis, Python geospatial ETL, a C# REST API, and a
React + Leaflet map frontend. Includes NDVI vegetation health scoring via Microsoft
Planetary Computer satellite imagery.

## External Drive Configuration

**IMPORTANT**: This entire project lives on an external drive. The drive MUST be mounted
before starting Docker, running any services, or editing code.

### Disk Layout
```

EXTERNAL DRIVE: /Volumes/Mac OS Extended 1/

├── Riparian_Buffer_POC/                # This repo (source code + solution)

└── DockerData/DockerDesktop/           # Docker images + volumes (~15GB+)

├── Images

└── Volumes                         # Persistent data (postgis, etc.)

```

### Project Root
All commands in this file assume you are in the project root:
```

cd "/Volumes/Mac OS Extended 1/Riparian_Buffer_POC"

```

### Pre-flight Check
Before running anything, verify the drive is mounted:
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

### Access URLs (Local Dev)
- Frontend: http://localhost (port 80)
- API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/swagger
- Aspire Dashboard: http://localhost:18888

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

**WARNING**: Never kill Aspire processes directly (`kill`, `pkill`, Activity Monitor). This can
restart the PostgreSQL container and corrupt data. Always use `./dev.sh --stop`.

### Drive Disconnect Recovery
If the external drive was disconnected (accidentally or for transport):
1. Reconnect the drive and wait for it to mount
2. Run `./dev.sh --reconnect` — checks drive I/O, stops zombie containers, shows data status
3. Run `./dev.sh` to start services
4. If data was lost: `./dev.sh --restore` (auto-backups are taken before full ETL runs)

### Build & Run
- Start everything: `./dev.sh`
- Start via Aspire directly: `dotnet run --project RiparianPoc.AppHost`
- Build solution: `dotnet build RiparianPoc.sln`
- Run API only: `dotnet run --project RiparianPoc.Api`
- Run ETL: `cd python-etl && python etl_pipeline.py`
- Frontend dev (hot-reload): `cd frontend && npm run dev` (runs on :3000)
- Frontend build: `cd frontend && npm run build`

### Testing
- C# tests: `dotnet test`
- Python tests: `cd python-etl && pytest`
- Frontend tests: `cd frontend && npm test`
- Lint C#: `dotnet format`
- Lint frontend: `cd frontend && npm run lint`

### Code Quality (SonarQube)
- Start server: `./dev.sh --sonar` (uses `docker-compose.sonar.yml`)
- Stop server: `./dev.sh --sonar-stop`
- Scan Python/TS/SQL: `./dev.sh --lint` (requires `SONAR_TOKEN` in `.env`)
- Scan C#: `./dev.sh --lint-dotnet`
- Dashboard: http://localhost:9000
- Token stored in `.env` (gitignored): `SONAR_TOKEN=squ_...`
- `dev.sh` auto-sources `.env` on startup

### Database

#### Data Persistence
PostgreSQL data is bind-mounted to `./pgdata/` (via `.WithDataBindMount("../pgdata")` in AppHost).
This survives Docker restarts, which happen frequently on the external drive. The `pgdata/` directory
is gitignored.

#### Backup & Restore
```
./dev.sh --backup     # Creates backups/ripariandb_YYYYMMDD_HHMMSS.dump (keeps latest 5)
./dev.sh --restore    # Restores from most recent backup (drops + recreates DB)
```
Always take a backup after a successful full ETL run. Backups use `pg_dump -Fc` (custom format).

#### Manual Database Access
Aspire auto-generates the PostgreSQL password. To connect manually:
```
# Get password from running container
PGPASSWORD=$(docker exec <postgres-container> printenv POSTGRES_PASSWORD)
psql -h localhost -p <mapped-port> -U postgres -d ripariandb
```

#### Schema Reset (if needed)
Apply schema files in order:
1. `sql/create_schemas.sql` — base schema (bronze/silver/gold tables, indexes)
2. `sql/incremental_migration.sql` — meta schema (etl_runs, constraints)

### Azure Deployment
- First time: `azd init` then `azd up`
- Redeploy: `azd deploy`
- Single service: `azd deploy --service api`
- Tear down: `azd down`

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
- In winter months, use `process_buffers('YYYY-06-01/YYYY-08-31')` with an explicit past date range

## Architecture

### Solution Structure
```

riparian-poc/

├── RiparianPoc.AppHost/           # .NET Aspire orchestrator (entry point)

├── RiparianPoc.Api/                # C# ASP.NET Core REST API (minimal APIs)

│   ├── Endpoints/

│   │   └── GeoDataEndpoints.cs     # Thin route handlers + DTO records

│   ├── Services/

│   │   ├── IGeoDataServices.cs     # ISpatialQueryService + IComplianceDataService

│   │   └── GeoDataServices.cs      # SpatialQueryService + ComplianceDataService impls

│   ├── Repositories/

│   │   ├── IPostGisRepository.cs   # Data access abstraction

│   │   └── PostGisRepository.cs    # Dapper + NpgsqlDataSource + GeoJSON

│   ├── Middleware/

│   │   ├── CorrelationMiddleware.cs      # X-Correlation-Id + X-Session-Id extraction

│   │   └── ExceptionHandlingMiddleware.cs # Global error → structured JSON

│   └── Models/

│       └── ApiErrorResponse.cs     # Structured error response record

├── RiparianPoc.ServiceDefaults/    # Shared Aspire service configuration

├── python-etl/                     # Python geospatial ETL pipeline

│   ├── etl_[pipeline.py](http://pipeline.py)             # Main orchestrated pipeline

│   ├── requirements.txt

│   └── Dockerfile

├── frontend/                       # React 18 + Leaflet + Tailwind

│   ├── src/

│   │   ├── App.tsx                 # Main map component

│   │   └── components/

│   │       └── NDVILayer.tsx        # NDVI heatmap overlay

│   ├── Dockerfile

│   └── nginx.conf

├── sql/

│   └── create_schemas.sql          # Database migration (source of truth for schema)

├── azure.yaml                      # Azure Developer CLI config

├── [CLAUDE.md](http://CLAUDE.md)                       # This file

└── RiparianPoc.sln

```jsx

### Medallion Architecture
- **bronze schema**: Raw ingested data. Minimal transformation. Preserves original attributes.
- **silver schema**: Spatial processing. Buffer generation, parcel intersections, compliance
  flagging, NDVI vegetation health scoring.
- **gold schema**: Aggregated analytics. Summary statistics by watershed.

Data flows one direction: bronze → silver → gold. Never write back upstream.

### Services and How They Connect
- **Aspire AppHost** orchestrates all services with automatic service discovery
- **PostgreSQL + PostGIS** is the shared data store (connection strings injected by Aspire)
- **C# API** reads from all three schemas, returns GeoJSON via NetTopologySuite
- **Python ETL** writes to bronze, silver, and gold schemas sequentially
- **React frontend** calls the C# API, renders on Leaflet map
- **Microsoft Planetary Computer** is accessed by the Python ETL for Sentinel-2 imagery (free, no API key)

### API Endpoints
- `GET /api/streams` — stream centerlines from bronze (GeoJSON)
- `GET /api/buffers` — riparian buffer polygons from silver (GeoJSON)
- `GET /api/buffers/health` — buffers with latest NDVI health (GeoJSON, LEFT JOIN LATERAL to vegetation_health)
- `GET /api/parcels` — parcels with compliance status (GeoJSON)
- `GET /api/focus-areas` — only focus area parcels (GeoJSON)
- `GET /api/vegetation/buffers/{bufferId}` — NDVI time series for a buffer
- `GET /api/summary` — gold layer compliance summary

## Conventions

### Spatial Data
- All geometry uses EPSG:4269 (NAD83) as the storage CRS
- Always cast to geography for distance/area calculations: `geom::geography`
- Use `ST_Buffer(geom::geography, meters)` — never buffer in degrees
- Distances are in meters internally, convert to feet for display (* 3.28084)
- Areas are in sq meters internally, convert to acres (/ 4046.86)
- Always use GiST indexes on geometry columns
- Use bounding box pre-filter (`&&`) before expensive spatial operations

### Field Mapping (API → Database)
Colorado Public Parcels REST API fields map to database columns:
- `parcel_id` → `parcel_id`
- `landUseDsc` → `land_use_desc`
- `landUseCde` → `land_use_code`
- `zoningDesc` → `zoning_desc`
- `owner` → `owner_name`
- `landAcres` → `land_acres`

This renaming happens in `etl_pipeline.py` during the `load_parcels()` step.

### NDVI & Phenology
- NDVI = (NIR - Red) / (NIR + Red), range -1 to +1
- Health thresholds calibrated for semi-arid San Juan Basin: healthy (>0.3), degraded (0.15–0.3), bare (<0.15)
- Only use imagery from peak growing season (June–August) for the San Juan Basin
- Tag every vegetation_health record with `season_context` column
- Dormant season readings should score as 'dormant', not 'bare'

### C# / .NET
Follow SOLID principles and the standards from the prompt library
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/dotnet).
- **SOLID**: SRP (one reason to change per class), OCP, LSP, ISP (small focused interfaces), DIP (depend on abstractions)
- ASP.NET Core minimal APIs (top-level Program.cs), .NET 10 features
- Use `sealed` classes when not designed for inheritance
- Use file-scoped namespaces (C# 10+)
- Use `record` types for DTOs and value objects
- Enable nullable reference types; use `?` annotations
- Constructor injection for all dependencies with null guards (`?? throw new ArgumentNullException`)
- Use `ILogger<T>` for structured logging with message templates (not string interpolation)
- Include `CancellationToken` on all async method signatures
- Use `async/await` for I/O; avoid `async void`
- Use `TypedResults` for endpoint return types (compile-time OpenAPI metadata)
- Add XML documentation comments on public APIs
- GeoJSON serialization via NetTopologySuite.IO.GeoJSON
- Connection string name: "ripariandb" (resolved by Aspire)
- CORS is open for development; lock down for production
- Tests: xUnit, AAA pattern (Arrange/Act/Assert), mock with NSubstitute or Moq
- Keep methods small and focused (< 20 lines ideally)
- Prefer immutability (records, init-only properties)

#### Data Access (Dapper)
- Use **Dapper** micro-ORM with `NpgsqlDataSource` (not EF Core for geo queries)
- `Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true` set in Program.cs
- `QueryAsync(CommandDefinition)` for dynamic GeoJSON rows; `QueryAsync<T>(CommandDefinition)` for typed DTOs
- Always pass `CancellationToken` via `CommandDefinition`
- GeoJSON deserialization: `ST_AsGeoJSON(geom) AS geojson` → extract `geojson` column, deserialize with `NetTopologySuite.IO.Converters.GeoJsonConverterFactory`, build `Feature` with remaining columns as `AttributesTable`

#### Service Layer Architecture
- **Endpoints** (`GeoDataEndpoints.cs`): Thin route handlers only — no SQL, no business logic. Inject service interfaces, call one method, return result.
- **Services** (`GeoDataServices.cs`): Own all SQL queries and business logic. Two ISP interfaces: `ISpatialQueryService` (5 spatial/GeoJSON methods) and `IComplianceDataService` (2 typed-result methods). Input validation here (e.g., `ArgumentException` for bad IDs).
- **Repository** (`PostGisRepository.cs`): Generic data access. `IPostGisRepository` with `QueryGeoJsonAsync` and `QueryAsync<T>`. Manages connection lifetime, GeoJSON deserialization, error handling for `NpgsqlException`.
- DI registration: all scoped (`AddScoped<TInterface, TImpl>`) in Program.cs

#### Observability (OpenTelemetry + Aspire)
- **Aspire ServiceDefaults** provides base OpenTelemetry config (tracing, metrics, logging with `IncludeScopes=true`, OTLP export)
- Three custom `ActivitySource` instances registered additively via `AddOpenTelemetry().WithTracing()`:
  - `RiparianPoc.Api.Repository` — database-level spans
  - `RiparianPoc.Api.SpatialQuery` — spatial service spans
  - `RiparianPoc.Api.ComplianceData` — compliance service spans
- Trace hierarchy: `HTTP request → Service span → Repository span → Npgsql auto-span`
- Each service/repo method: `using var activity = Source.StartActivity("Name")` + `activity?.SetTag()` for result counts and timing

#### Correlation & Session Tracking
- `CorrelationMiddleware` extracts `X-Correlation-Id` (or uses W3C TraceId) and `X-Session-Id` headers
- Sets `Activity.Current` tags: `correlation.id`, `session.id`, `client.ip`
- `ILogger.BeginScope()` adds `CorrelationId`, `SessionId`, `ClientIp` to all downstream logs
- Response includes `X-Correlation-Id` header; CORS exposes it via `WithExposedHeaders`
- In Aspire Dashboard: filter traces by `session.id` tag to see all requests for one user session

#### Error Handling (Defense in Depth)
- `ExceptionHandlingMiddleware` catches all unhandled exceptions globally
- Exception type → HTTP status mapping: `NpgsqlException` → 503, `ArgumentException` → 400, `KeyNotFoundException` → 404, `OperationCanceledException` → 504, default → 500
- 4xx errors expose `ex.Message` (user-facing); 5xx use generic messages
- `ApiErrorResponse` record: `{ error, correlationId, statusCode, detail? }` — `detail` only in Development
- Repository catches `NpgsqlException`, logs with timing context, sets `Activity.SetStatus(Error)`, rethrows
- Services validate input and throw `ArgumentException` for invalid parameters

### Python
Follow SOLID principles and the standards from the prompt library
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/python).
- **SOLID**: Use `Protocol` classes (PEP 544) for interfaces, constructor injection via `__init__`
- Python 3.11+ features; follow PEP 8 (snake_case functions/variables, PascalCase classes)
- Type hints on ALL function parameters and return types (PEP 484)
- Use `@dataclass(frozen=True)` for data structures; Pydantic for validation
- Google-style docstrings on all public functions and classes
- Custom exception classes for domain errors; don't catch bare `Exception`
- Use context managers (`with`) for all resource management
- Use the `logging` module with appropriate levels; never log sensitive data
- Use SQLAlchemy + `text()` for all parameterized SQL
- Use GeoPandas for reading/writing spatial data to PostGIS
- Use `planetary_computer.sign_inplace` for Planetary Computer STAC access
- Use `rasterio.mask.mask()` to clip rasters to buffer geometries
- Pipeline functions run sequentially: watershed → streams → parcels → buffers → compliance → summary
- Tests: pytest, AAA pattern, fixtures for setup, pytest-mock for mocking
- Keep functions small (< 25 lines ideally), prefer comprehensions and generators
- Prefer immutable data (frozen dataclasses, tuples)

### SQL (PostgreSQL / PostGIS)
Follow the standards from the prompt library
(https://github.com/emeraldleaf/Prompt-and-Github-Copilot-setup/tree/main/prompt-library/sql).
- **Naming**: snake_case for tables, columns, indexes (e.g., `idx_streams_geom`)
- Always specify column names in SELECT — never use `SELECT *` in production code
- Use CTEs (Common Table Expressions) for complex multi-step queries
- Use parameterized queries only — never concatenate user input
- Define foreign key constraints for referential integrity
- Include audit timestamps (`imported_at`, `created_at`, `processed_at`) on all tables
- Use `EXISTS` instead of `IN` for subqueries with large datasets
- Use table aliases for readability in JOINs
- Add comments on complex logic
- Use transactions for multi-step write operations
- Use appropriate data types and sizes; prefer NUMERIC for precision
- Use bounding box pre-filter (`&&`) before expensive PostGIS spatial operations
### Frontend
- React 18 + TypeScript
- Leaflet via react-leaflet
- Vite for build tooling
- Tailwind CSS for styling
- API base URL from `VITE_API_URL` environment variable
- NDVI heatmap uses leaflet.heat plugin with real `mean_ndvi` values from `/api/buffers/health`
- Satellite basemap toggle: ESRI World Imagery as alternative TileLayer (use React `key` prop to force remount on switch)
- Buffer zones colored by NDVI health category: healthy (green), degraded (yellow), bare (red), no data (default)
- Session tracking: `crypto.randomUUID()` generated per page load, sent as `X-Session-Id` header on every fetch
- `fetchJson<T>` helper: sends session header, logs `X-Correlation-Id` from response, parses `ApiErrorResponse` on failure

### Code Quality Files
- `docker-compose.sonar.yml` — SonarQube server + PostgreSQL backend (not embedded H2)
- `sonar-project.properties` — Scanner config for Python + TypeScript + SQL
- `.vscode/settings.json` — SonarQube connected mode project binding
- `.vscode/extensions.json` — Recommended VS Code extensions (SonarQube for IDE, etc.)
- `.env` — Environment secrets (gitignored), stores `SONAR_TOKEN`

## Do Not Modify (without explicit request)
- `sql/create_schemas.sql` — this is the schema source of truth
- `azure.yaml` — Azure deployment config
- `RiparianPoc.AppHost/Program.cs` — Aspire orchestration
- Do not change coordinate reference systems (EPSG:4269 for storage)
- Do not add NuGet or npm packages without asking
- Do not reorganize project structure or move files between directories
- Do not change field mappings in etl_pipeline.py without updating the schema

## Common Patterns

### Adding a new API endpoint
1. Add the method to the appropriate service interface (`ISpatialQueryService` or `IComplianceDataService`) in `Services/IGeoDataServices.cs`
2. Implement in `Services/GeoDataServices.cs` — write SQL with `ST_AsGeoJSON(geom) AS geojson`, call `_repository.QueryGeoJsonAsync()` or `_repository.QueryAsync<T>()`
3. Add `using var activity = Source.StartActivity(...)` and completion logging
4. Add a thin route handler in `Endpoints/GeoDataEndpoints.cs` that injects the service and calls the method
5. Return `TypedResults.Ok(result)`

### Adding a new ETL step
1. Add a function in `etl_pipeline.py`
2. Use `engine.connect()` + `text()` for SQL, or `gpd.read_postgis()` for reads
3. Call it from `main()` in the correct pipeline order
4. Add logging at start and end of the function

### Adding a new map layer
1. Fetch from API in `App.tsx` useEffect
2. Add a `<GeoJSON>` component with style function
3. Add popup via `onEachFeature`
4. Add to legend

## Data Sources
- NHDPlus V2.1: https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/NHDPlusV21/FeatureServer
- Colorado Parcels: https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0
- USDA Watersheds: https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_Watersheds_01/MapServer
- Sentinel-2 via Planetary Computer: https://planetarycomputer.microsoft.com/api/stac/v1
- Study area: San Juan Basin, HUC8 code 14080101
```