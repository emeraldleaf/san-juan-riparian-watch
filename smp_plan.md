# SMP Dataset Integration & Composite Health Scoring Plan

> Based on the [Colorado Stream Management Program (SMP)](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/biological-conditions/riparian-vegetation/) riparian vegetation assessment methodology and [FACStream/COSHAF assessment framework](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/assessment-framework/).

## Summary

Integrate six datasets from the Colorado SMP methodology (NWI, NLCD, LANDFIRE EVT/EVH, SSURGO, NAIP, LiDAR/3DEP) into the existing medallion architecture, then build a composite riparian health score in the gold layer using the SMP's **80/10/10** weighting (vegetation structure / habitat connectivity / contributing area).

The existing parcel intersection stays as-is and gets improved later once NLCD land use data provides meaningful "contributing area" context.

Work is phased from quickest wins (NAIP basemap, NWI polygons) through raster processing (NLCD, LANDFIRE) to the most complex (LiDAR 3DEP canopy), with composite scoring built after all data layers are in place.

### Key Architectural Decision

- **Vector datasets** (NWI, SSURGO) follow the existing `ArcGISFeatureClient` → `PostGISWriter` pattern in `python-etl/etl_pipeline.py`.
- **Raster datasets** (NLCD, LANDFIRE) follow the `rasterio` + zonal-stats pattern from `python-etl/ndvi_processor.py`.
- All new data writes to new bronze/silver tables; the composite score lives in a new gold table.

---

## SMP Background: The 80/10/10 Vegetation Scoring Model

From the [Riparian Vegetation page](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/biological-conditions/riparian-vegetation/):

### Vegetation Structure (80%) — 9 sub-metrics

| Sub-metric              | Remote Sensing Proxy          | Dataset           | Feasibility |
|-------------------------|-------------------------------|-------------------|-------------|
| Vertical complexity     | LANDFIRE EVH (vegetation height) | LANDFIRE EVH   | High        |
| Canopy species          | LANDFIRE EVT (vegetation type)   | LANDFIRE EVT   | Medium      |
| Shrub layer             | LANDFIRE EVT + NLCD              | LANDFIRE + NLCD | Medium      |
| Invasive species        | EDDMapS occurrence points        | EDDMapS         | Future      |
| Patchiness              | NLCD fragmentation analysis      | NLCD            | High        |
| Native regeneration     | NDVI temporal trend              | Sentinel-2      | Medium (have this!) |
| Floodplain position     | Buffer distance                  | Already in schema | Done       |
| Native vs non-native    | LANDFIRE EVT classification      | LANDFIRE EVT    | Medium      |
| Age class structure     | LiDAR canopy height model        | 3DEP            | Complex     |

### Habitat Connectivity (10%)

Corridor continuity between patches — approximated by measuring gaps in NLCD forest/shrub cover along the stream corridor.

### Contributing Area (10%)

Surrounding land use influence — NLCD land cover in a wider buffer zone; replaces simplistic parcel overlap.

---

## Dataset Reference

| Dataset       | What It Provides                          | Source Type | API / Access                                                                                      | Can Automate? |
|---------------|-------------------------------------------|-------------|---------------------------------------------------------------------------------------------------|---------------|
| **NWI**       | Wetland polygons within/near buffers       | Vector      | [FWS ArcGIS REST](https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0) | Yes           |
| **NLCD** (30m)| Land cover classification around buffers   | Raster      | [MRLC WCS](https://www.mrlc.gov/data-services-page) or COG                                       | Yes           |
| **LANDFIRE**  | Existing Vegetation Type/Height, fire risk | Raster      | [LANDFIRE Image Services](https://lfps.usgs.gov/arcgis/rest/services/) or direct download         | Yes           |
| **NAIP** (1m) | High-res aerial imagery basemap            | Tile        | [USDA NAIP WMS](https://gis.apfo.usda.gov/arcgis/rest/services/NAIP/)                            | Yes (basemap) |
| **SSURGO**    | Hydric soils, soil type under buffers      | Vector      | [NRCS SDM REST](https://SDMDataAccess.sc.egov.usda.gov/) + ArcGIS spatial                        | Yes           |
| **LiDAR**     | Canopy height, terrain, vertical complexity| Raster/EPT  | [USGS 3DEP on Planetary Computer](https://planetarycomputer.microsoft.com/dataset/3dep-lidar-copc) | Complex       |

---

## Phase 1 — Quick Wins (frontend + vector)

### Step 1: NAIP Basemap Toggle

**Scope**: Frontend only — no backend changes.

**Changes**:
- `frontend/src/App.tsx`: Add third basemap option `'naip'` alongside `'street'` and `'satellite'`
- USDA NAIP tile URL: `https://gis.apfo.usda.gov/arcgis/rest/services/NAIP/USDA_CONUS_PRIME/ImageServer/tile/{z}/{y}/{x}`
- Update basemap toggle button to cycle through three options

**Verification**: Toggle button shows "Street Map" → "Satellite" → "NAIP Aerial" → cycles back.

---

### Step 2: NWI Wetland Polygons (Full Stack)

**Pattern**: Same as parcels — ArcGIS REST → bronze table → silver intersection → API → frontend layer.

#### Schema (`sql/create_schemas.sql`)

```sql
-- Bronze: Raw NWI wetland polygons
CREATE TABLE bronze.nwi_wetlands (
    id              SERIAL PRIMARY KEY,
    wetland_type    TEXT,
    cowardin_code   TEXT,
    acres           NUMERIC(12, 4),
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_nwi_wetlands_geom ON bronze.nwi_wetlands USING gist (geom);

-- Silver: Buffer-wetland intersection
CREATE TABLE silver.buffer_wetlands (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    wetland_id      INTEGER NOT NULL REFERENCES bronze.nwi_wetlands(id),
    overlap_area_sq_m NUMERIC(14, 2),
    wetland_pct_of_buffer NUMERIC(5, 2),
    wetland_type    TEXT,
    cowardin_code   TEXT,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_wetlands_buffer_id ON silver.buffer_wetlands (buffer_id);
```

#### ETL (`python-etl/etl_pipeline.py`)

- `NWI_URL = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0"`
- Add `load_nwi_wetlands()` method — uses `ArcGISFeatureClient` with watershed envelope filter
- Field map: `WETLAND_TYPE → wetland_type`, `ATTRIBUTE → cowardin_code`, `ACRES → acres`
- Add `analyze_buffer_wetlands()` — SQL intersection of `silver.riparian_buffers` ∩ `bronze.nwi_wetlands`
- Update `run()` pipeline: call after `load_parcels()`, analyze after `generate_buffers()`

#### API

- `ISpatialQueryService.GetWetlandsAsync()` → `GET /api/wetlands` (GeoJSON)
- `IComplianceDataService.GetBufferWetlandsAsync(int bufferId)` → `GET /api/buffers/{bufferId}/wetlands`

#### Frontend

- New `wetlands` state + fetch in `useEffect`
- `<GeoJSON>` layer with blue/teal fill styling
- Popup: Wetland Type, Cowardin Code, Acres
- Legend entry: "NWI Wetlands" with teal color
- Layer toggle (checkbox or button) to show/hide

**Verification**: NWI polygons visible on map. Click → popup with Cowardin code. `GET /api/wetlands` returns GeoJSON.

---

## Phase 2 — Raster Processing (NLCD + LANDFIRE)

### Step 3: Raster Processing Framework

**New file**: `python-etl/raster_processor.py`

Generalizes the rasterio clipping pattern from `ndvi_processor.py`:
- `RasterSource` protocol — provides raster data for a bbox
- `ZonalStatsWriter` protocol — persists results
- `compute_zonal_stats()` — takes raster, buffer geometries, computes per-buffer statistics
- Reuses `rasterio.mask.mask()` and `rasterio.features.geometry_mask()` patterns

---

### Step 4: NLCD Land Cover Extraction

#### Schema

```sql
-- Silver: NLCD class distribution per buffer
CREATE TABLE silver.buffer_land_cover (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    nlcd_class      INTEGER NOT NULL,
    nlcd_description TEXT NOT NULL,
    pixel_count     INTEGER NOT NULL,
    area_pct        NUMERIC(5, 2),
    is_natural      BOOLEAN NOT NULL DEFAULT FALSE,
    acquisition_year INTEGER,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_land_cover_buffer_id ON silver.buffer_land_cover (buffer_id);
```

#### ETL (`python-etl/nlcd_processor.py`)

- MRLC WCS service or pre-downloaded COG for San Juan Basin
- For each buffer: clip NLCD raster → count pixels per class → compute area percentages
- NLCD class lookup dict: code → description → natural/developed flag
- Key classes: 41=Deciduous Forest, 42=Evergreen Forest, 43=Mixed Forest, 52=Shrub/Scrub, 71=Grassland, 90=Woody Wetlands, 95=Emergent Herbaceous Wetlands, 21/22/23/24=Developed

#### API

- `GET /api/buffers/{bufferId}/landcover` — NLCD class distribution for a buffer

#### Frontend

- NLCD breakdown in buffer popup (bar chart or list of land cover classes with percentages)

**Verification**: Click buffer → popup shows NLCD class breakdown. `GET /api/buffers/1/landcover` returns class distribution.

---

### Step 5: LANDFIRE EVT/EVH Extraction

#### Schema

```sql
-- Silver: LANDFIRE vegetation structure per buffer
CREATE TABLE silver.buffer_vegetation_structure (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    evt_code        INTEGER,
    evt_name        TEXT,
    evh_class       TEXT,
    mean_height_m   NUMERIC(6, 2),
    dominant_lifeform TEXT,
    pixel_count     INTEGER,
    area_pct        NUMERIC(5, 2),
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_veg_structure_buffer_id ON silver.buffer_vegetation_structure (buffer_id);
```

#### ETL (`python-etl/landfire_processor.py`)

- LANDFIRE EVT (Existing Vegetation Type) and EVH (Existing Vegetation Height) rasters
- EVT → species composition, shrub presence, native cover
- EVH → vertical complexity (vegetation height classes)
- Bundle LANDFIRE lookup CSVs for code → name/lifeform mapping

#### API

- `GET /api/buffers/{bufferId}/vegetation-structure` — EVT/EVH for a buffer

**Verification**: `GET /api/buffers/1/vegetation-structure` returns EVT/EVH data.

---

## Phase 3 — SSURGO Soils

### Step 6: SSURGO Hydric Soils

#### Schema

```sql
-- Bronze: Raw SSURGO soil map units
CREATE TABLE bronze.ssurgo_soils (
    id              SERIAL PRIMARY KEY,
    mukey           TEXT NOT NULL UNIQUE,
    musym           TEXT,
    muname          TEXT,
    hydric_rating   TEXT,
    hydric_pct      NUMERIC(5, 2),
    geom            geometry(MultiPolygon, 4269) NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ssurgo_soils_geom ON bronze.ssurgo_soils USING gist (geom);
CREATE INDEX idx_ssurgo_soils_mukey ON bronze.ssurgo_soils (mukey);

-- Silver: Buffer-soil intersection
CREATE TABLE silver.buffer_soils (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    soil_id         INTEGER NOT NULL REFERENCES bronze.ssurgo_soils(id),
    overlap_area_sq_m NUMERIC(14, 2),
    hydric_rating   TEXT,
    hydric_pct      NUMERIC(5, 2),
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_soils_buffer_id ON silver.buffer_soils (buffer_id);
```

#### ETL

- NRCS SDM REST API for tabular hydric data + ArcGIS spatial for polygons
- `load_ssurgo_soils()` → bronze
- `analyze_buffer_soils()` → silver intersection

#### API

- `GET /api/soils` — soil polygons as GeoJSON
- `GET /api/buffers/{bufferId}/soils` — soil overlaps for a buffer

#### Frontend

- Optional soil layer toggle with hydric rating coloring

**Verification**: Soil polygons on map with hydric rating popup.

---

## Phase 4 — Composite Health Score

### Step 7: SMP-Aligned Composite Scoring

#### Schema

```sql
-- Gold: Composite riparian health score per buffer
CREATE TABLE gold.buffer_health_score (
    id                          SERIAL PRIMARY KEY,
    buffer_id                   INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    -- Vegetation Structure sub-scores (0-10 scale)
    ndvi_score                  NUMERIC(5, 2),
    vertical_complexity_score   NUMERIC(5, 2),
    species_composition_score   NUMERIC(5, 2),
    shrub_layer_score           NUMERIC(5, 2),
    patchiness_score            NUMERIC(5, 2),
    native_regeneration_score   NUMERIC(5, 2),
    native_cover_score          NUMERIC(5, 2),
    -- Weighted category scores (0-100 scale)
    vegetation_structure_score  NUMERIC(5, 2),
    connectivity_score          NUMERIC(5, 2),
    contributing_area_score     NUMERIC(5, 2),
    -- Composite
    composite_score             NUMERIC(5, 2),
    score_grade                 CHAR(1) CHECK (score_grade IN ('A','B','C','D','F')),
    scored_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_health_score_buffer_id ON gold.buffer_health_score (buffer_id);
CREATE INDEX idx_buffer_health_score_grade ON gold.buffer_health_score (score_grade);
```

#### Scoring Logic (`python-etl/health_scorer.py`)

| Category                | Weight | Input Data                                  | Scoring Method                                                  |
|-------------------------|--------|---------------------------------------------|-----------------------------------------------------------------|
| Vegetation Structure    | 80%    | NDVI, LANDFIRE EVT/EVH, NLCD               | 7 sub-metrics scored 0–10, averaged, scaled to 0–100            |
| Habitat Connectivity    | 10%    | NLCD along stream corridor                  | Measure gaps in forest/shrub cover between adjacent buffers     |
| Contributing Area       | 10%    | NLCD in wider (150m) buffer zone            | Ratio of natural vs developed land cover                        |

**Composite**: `composite = 0.80 × vegetation_structure + 0.10 × connectivity + 0.10 × contributing_area`

**Grades**: A (≥80), B (60–79), C (40–59), D (20–39), F (<20)

#### API

- `GET /api/buffers/scores` — buffers with composite health scores as GeoJSON
- Update `gold.riparian_summary` with aggregate composite score

#### Frontend

- New visualization mode: color buffers by composite grade (A=dark green, B=light green, C=yellow, D=orange, F=red)
- Toggle between "NDVI Health" and "SMP Score" views
- Updated header stats with aggregate composite score

**Verification**: Buffers colored by A–F grade. Header shows aggregate score.

---

## Phase 5 — LiDAR Canopy Height (Advanced)

### Step 8: USGS 3DEP Canopy Height Models

#### Schema

```sql
-- Silver: LiDAR-derived canopy metrics per buffer
CREATE TABLE silver.buffer_canopy (
    id              SERIAL PRIMARY KEY,
    buffer_id       INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
    mean_height_m   NUMERIC(6, 2),
    max_height_m    NUMERIC(6, 2),
    p95_height_m    NUMERIC(6, 2),
    canopy_cover_pct NUMERIC(5, 2),
    height_std_dev  NUMERIC(6, 2),
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_buffer_canopy_buffer_id ON silver.buffer_canopy (buffer_id);
```

#### ETL (`python-etl/lidar_processor.py`)

- USGS 3DEP CHM tiles via Planetary Computer STAC or Entwine Point Tiles
- Clip to each buffer geometry, compute height statistics (mean, max, P95, cover %)
- Most complex processor — LiDAR data is large, may require tiling/chunking

#### Integration

- Feed `mean_height_m` into vegetation structure score (age class structure sub-metric) in `health_scorer.py`
- `GET /api/buffers/{bufferId}/canopy` endpoint
- Canopy height stats in buffer popup

**Verification**: `GET /api/buffers/1/canopy` returns height stats. Composite score incorporates age-class data.

---

## Cross-Cutting Changes

### ETL Pipeline Order

```
watershed → streams → parcels → NWI → SSURGO
  → buffers → compliance → buffer_wetlands → buffer_soils
  → NLCD → LANDFIRE → LiDAR
  → composite scoring → summary
```

### dev.sh Updates

```bash
./dev.sh --update datasets    # Run only new dataset processors (NWI, NLCD, LANDFIRE, SSURGO, LiDAR)
./dev.sh --update score       # Recompute composite scores from existing data
```

### Dependencies

No new Python packages needed — `rasterio`, `geopandas`, `pystac_client`, `planetary_computer`, `shapely`, `numpy` are already in `requirements.txt` from the NDVI pipeline.

---

## Decisions Log

| Decision                     | Choice                                                                                     |
|------------------------------|--------------------------------------------------------------------------------------------|
| Parcels                      | Keep as-is; improve later with NLCD-based contributing area scoring                        |
| Raster approach              | Local/WCS download + rasterio zonal stats (same pattern as NDVI)                           |
| NAIP                         | Basemap only (no analytical processing), via USDA tile service                             |
| Scoring model                | 80/10/10 weighted composite per SMP methodology, A–F letter grades                         |
| Phase order                  | NAIP/NWI first (visible fast) → raster datasets → scoring → LiDAR last (most complex)     |
| New packages                 | None — reuse existing rasterio/geopandas/planetary_computer stack                          |
| Schema migrations            | Additive only — new tables, no changes to existing tables                                  |

---

## Sources

- [Riparian Vegetation — Colorado SMP Library](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/biological-conditions/riparian-vegetation/)
- [Assessment Framework — Colorado SMP Library](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/assessment-framework/)
- [Biological Conditions — Colorado SMP Library](https://www.coloradosmp.org/smp-nuts-and-bolts/assess-conditions-risk/biological-conditions/)
- [CO-RIP Riparian Vegetation Dataset (MDPI)](https://www.mdpi.com/2220-9964/7/10/397)
- [GIS Data — Colorado Decision Support Systems](https://cdss.colorado.gov/gis-data)
- [MRLC Data Services](https://www.mrlc.gov/data-services-page)
- [LANDFIRE Data Distribution](https://landfire.gov/data)
- [NWI Wetlands MapServer](https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer)
- [USGS 3DEP on Planetary Computer](https://planetarycomputer.microsoft.com/dataset/3dep-lidar-copc)
