# Feature spec — Stage 1: Riparian extent delineation

**Produced by `/feature-spec` · 2026-07-03 · feeds the encoding loop**
Related: [ADR — delineation over hydrology buffers](../decisions/2026-07-03-delineation-over-hydrology-buffers.md)

## Value gate

1. **Who needs this / what breaks without it?** Land & water managers (and the project's
   credibility). Without correct extent, every downstream product is built on the false
   fixed-buffer assumption. **Passes.**
2. **Would we build it if it cost a week?** Yes — it is the foundation the whole pipeline
   hangs off. **Passes.**
3. **Who owns saying no?** Joshua Dell (solo). **Named.**

## Goal

Produce a reliable map of **where woody riparian vegetation actually is** in the San Juan
Basin study area, independent of fixed hydrology buffers, with a per-pixel confidence layer.

## Revision 2026-07-03b — AOI, network-first structure, reference layers

Scope decisions (supersede the small-AOI prototype framing below where they conflict):

- **AOI = San Juan River hydrologic watershed (HUC), CO + NM**, headwaters → lowlands.
  Organizing unit = **HUC12** (each HUC12 is an independently processable, restartable tile).
  Segmentation = **NHD flowlines split into ~250 m reaches**.
- **Operational definition (single, basin-wide):** *riparian = vegetation in the
  hydrologically connected corridor showing groundwater-subsidized phenology/structure.*
  One definition across both states so the basin map stays coherent at the CO/NM seam.
- **Stage 1 is network-first, three sub-stages:**
  - **1A — Candidate envelope (physics first):** HAND / valley-bottom from the 3DEP DEM.
    Answers "where could riparian exist at all?" — constrains inference, cuts false positives
    and compute. Uplands eliminated early.
  - **1B — EO delineation inside the envelope:** the verified STAC pipeline (S2 phenology +
    SWIR moisture + optional S1 + multi-year stats).
  - **1C — Weak-label fusion:** WorldCover ∧ io-lulc ∧ NWI as supervision/QA — *not* the
    definition (avoid "green near water" = riparian).
- **Reference layers (validation truth + priors, not a dependency):**
  [NMRipMap v2.0+](https://nhnm.unm.edu/riparian/NMRipMap) on NM reaches;
  [CO-RIP](https://datadryad.org/dataset/doi:10.5061/dryad.3g55sv8) on CO reaches (if it
  covers the AOI); San Juan NF GIS as fallback. **Validate NM vs CO separately** (different
  source methodologies), then reconcile the border seam. Don't let Stage 1 *depend* on them
  (avoids a cliff at the NM/CO boundary).
- **Outputs are dual:** a raster `riparian_probability` **and** a per-reach table
  (`%riparian_cover`, `confidence`, delineation `quality_flags`). Validation stratified by
  stream order / valley type (headwaters vs alluvial vs ag interface).
- **Delivery = web app:** map UI (extent / condition / change + baseline-vs-OlmoEarth
  disagreement overlay) + API serving tiles/GeoJSON + reach summaries; heavy ML is a batch
  pipeline that publishes layers to PostGIS/COGs. ML does **not** run in the browser.
- **Compute:** baseline (HAND + indices + RF) is CPU/IO-bound — GPU is nice-to-have. "OlmoEarth
  everywhere" (basin-wide embeddings, optional fine-tune) is GPU-recommended; persist an
  **embedding store** so classifiers can be re-run without re-encoding.

**Status:** the small-AOI baseline slice (below) is verified end-to-end incl. DB write. The
HUC12/HAND/reach-table/reference-layer items are the next build-out.

*(Two-implementations test: RF/XGBoost-on-features and OlmoEarth-embeddings could both
satisfy this — it's a goal, not an implementation.)*

## Acceptance criteria (externally observable)

- A `silver.riparian_extent` layer exists with, per cell/polygon: `is_riparian` (bool),
  `riparian_probability` (0–1), `method` (`rf` | `olmoearth`), `model_version`, and
  `processed_at`.
- Extent is served as GeoJSON via a new endpoint (see Affects) and renders as a map layer
  with a legend and a probability-driven style.
- **Two methods produce comparable outputs** over the same AOI so they can be diffed
  (baseline RF/XGBoost vs. OlmoEarth), with agreement/disagreement inspectable.
- **Validation report** exists: spatial-CV metrics (precision/recall/F1, PR-AUC) against a
  held-out reference (one of LANDFIRE/NLCD/NWI held out) + NAIP visual spot-check notes.
- Runs **CPU-only** end-to-end on the local Mac for the study-area AOI.
- Failure modes handled: no imagery for a date/AOI (skip + log, don't crash), empty
  weak-label intersection (fail the run with a clear message), STAC endpoint unavailable
  (retry/backoff then fail the run), all-cloud season (widen the window or report gap).

## Affects

- **New ETL:** `python-etl/stac_datacube.py` (STAC query → xarray cube), `feature_builder.py`
  (index/texture/terrain/SAR feature stack), `delineation_baseline.py` (RF/XGBoost),
  `delineation_olmoearth.py` (embeddings + light head), `delineation_validate.py` (spatial CV).
- **New `entrypoint.py` mode:** `--mode delineate` (sub-options `baseline` | `olmoearth` | `both`).
- **New schema:** `sql/delineation_migration.sql` → `silver.riparian_extent`
  (+ weak-label staging in bronze). **Do not edit `create_schemas.sql`** — additive migration.
- **New API:** `GET /api/riparian/extent` (+ `?method=`) — service method in
  `ISpatialQueryService`/`GeoDataServices.cs`, query via `PostGisRepository.QueryGeoJsonAsync`,
  thin handler in `GeoDataEndpoints.cs`.
- **New map layer:** extent + probability in `App.tsx` with legend.
- **`generate_buffers()`** demoted from foundation (kept temporarily for A/B against extent).
- **New dependencies (require explicit sign-off):** `pystac-client`, `stackstac`/`odc-stac`,
  `xarray`, `rioxarray`, `scikit-learn`, `xgboost`, `olmoearth-pretrain-minimal`, `torch` (CPU).

## Upstream dependencies (assumptions that could shift)

- **Planetary Computer STAC** collections `sentinel-2-l2a`, `sentinel-1-rtc`, `3dep-seamless`;
  band order for OlmoEarth S2 L2A is fixed `[B02,B03,B04,B08,B05,B06,B07,B8A,B11,B12,B01,B09]`.
- **Peak growing season June–August** for the San Juan Basin; dry-season contrast is the
  phreatophyte discriminator — assumes multi-year archive depth, not single-scene realtime.
- **Weak-label maps** (LANDFIRE EVT / NLCD / NWI) remain the supervision source; their class
  definitions and vintages are load-bearing.
- **CRS EPSG:4269** storage; reprojection handled in the datacube step.
- If any shift mid-build (e.g. a collection id changes, OlmoEarth band order updates), flag
  the spec as invalidated.

## Non-functional constraints

- CPU-only on the local Mac (external drive); no GPU.
- STAC scene selection must be queryable/reproducible (auditable data step, not manual pulls).
- ETL incremental mode must not wipe existing NDVI/vegetation_health data.

## Constraints from CLAUDE.md

- **Spatial CRS + geography casts** — EPSG:4269 storage, `geom::geography` for area/distance,
  GiST index, `&&` bbox pre-filter → CLAUDE.md "Conventions → Spatial Data". See CLAUDE.md.
- **Medallion one-way flow** — weak labels land in bronze; extent in silver; never write
  upstream → CLAUDE.md "Medallion Architecture". See CLAUDE.md.
- **Do Not Modify** — additive `*_migration.sql` only; no `create_schemas.sql` edit; **no new
  packages without asking** (this spec lists several — get sign-off) → CLAUDE.md "Do Not
  Modify". See CLAUDE.md.
- **Python standards** — type hints, `Protocol` interfaces, frozen dataclasses, SQLAlchemy
  `text()`, GeoPandas for PostGIS I/O, functions < 25 lines → CLAUDE.md "Python". See CLAUDE.md.
- **Service-layer boundaries** — endpoint thin, SQL in service, generic repository →
  CLAUDE.md "Service Layer Architecture". See CLAUDE.md.
- **Async + CancellationToken + Observability** — on the new endpoint/service/repo path →
  CLAUDE.md "C# / .NET" + "Observability". See CLAUDE.md.

## Significance check

**ADR: yes** — replaces a core method, adds an ML integration + STAC datacube architecture +
new schema. Drafted at `docs/decisions/2026-07-03-delineation-over-hydrology-buffers.md`.

## Outputs / scaffolding order

1. `sql/delineation_migration.sql` (schema first).
2. `stac_datacube.py` → `feature_builder.py` (get a feature cube over the AOI, verify shapes).
3. `delineation_baseline.py` (RF/XGBoost) — the label-efficient baseline, first end-to-end map.
4. `delineation_validate.py` (spatial CV) — establish the number to beat.
5. `delineation_olmoearth.py` — the FM contender; diff against baseline.
6. API endpoint + map layer.

Canonical reference to mirror for raster-clip-to-geometry: `python-etl/ndvi_processor.py`.

## Gap check (holes closed)

- Failure modes named (no imagery / empty labels / STAC down / all-cloud). ✅
- "The ETL" named down to specific modules + `--mode delineate`. ✅
- Spatial constraints named to CRS + geography cast, not "follow the spatial rules." ✅
- STAC deps named to collection ids + OlmoEarth band order. ✅
- Open hole: exact reach/grid cell size for aggregation (100 m per Pace LUI vs native 10 m) —
  **decide before Stage 2**; Stage 1 delineates at native S2 10 m and aggregates later.

## Closing the loop

> **This spec captures the handoff.** Once you've shipped Stage 1, what did building it
> surface? Any "we should never write this again" or "we should always do this when" — encode
> it across the 5 surfaces. The spec is ephemeral; the lessons are how the loop compounds.
