---
description: Scaffold a new Python ETL step / processor following the Protocol-DI + pure-function conventions
argument-hint: <what the step does + source, e.g. "compute NDMI moisture index per riparian cell">
disable-model-invocation: true
---

# /add-etl-step

Scaffold a new ETL step that respects the project's Python conventions and medallion flow.
See CLAUDE.md "Python" + "Medallion Architecture" + "Common Patterns".

`$ARGUMENTS` describes the step + its data source. If empty, ask.

## Decide first: which home does the step belong in?

- **Riparian AI work** (delineation, health/condition, invasives, reaches, validation, STAC
  datacube/features) → add a module in the domain-organized **`riparian/` package**:
  `riparian/{datacube,delineation,health,reaches,validation}/`. Import intra-package via
  `riparian.<domain>.<module>`. Mirror the existing modules (e.g. `riparian/delineation/runner.py`).
- **A legacy source ingest** (new external raster/vector API following the old pattern) → add a
  flat `python-etl/<name>_processor.py` and wire it into `entrypoint.py` as a `--mode`
  (mirror `ndvi_processor.py`).
- **A step in the existing legacy pipeline** (simple transform on ingested data) → a function
  in `etl_pipeline.py`, called from `main()` in order.

## Conventions (non-negotiable)

- **Type hints** on every param + return. Google-style docstrings on public functions/classes.
- **Protocol interfaces + constructor injection** for I/O boundaries (imagery searcher, DB
  writer) so the step is testable with fakes — reference `ndvi_processor.py`
  `ImagerySearcher`/`NdviWriter`. Frozen dataclasses for data structures.
- **Separate pure functions from I/O** — put index math / stats in pure functions (like
  `calculate_ndvi`, `compute_ndvi_stats`) so they unit-test without network or DB.
- **SQL is SQLAlchemy `text()` parameterized** — never f-string SQL. GeoPandas for PostGIS
  reads (`gpd.read_postgis(...)` then `gdf.rename_geometry("geometry")` — DB column is `geom`).
- **STAC**: `planetary_computer.sign_inplace`; for datacubes reuse `riparian.datacube.stac`
  and its `spatial_dims()` helper (geographic cubes name dims `latitude`/`longitude`, not `x`/`y`).
- **Medallion direction**: write to the correct schema — bronze (raw/weak-labels), silver
  (derived spatial), gold (aggregates). Never write upstream.
- **Log at start and end** of the step. Functions < 25 lines; no bare `except Exception`.

## Guardrails

- **New schema → additive `sql/*_migration.sql`**, never edit `create_schemas.sql`.
- **No new pip packages without asking** (they go in `requirements.txt` after sign-off).
- **Peak growing season (June–August)** for San Juan Basin imagery; tag season context where
  relevant. See CLAUDE.md "NDVI & Phenology".
- Verify against a small AOI before claiming it works (see `verification-before-completion`).
