# ADR: Learned riparian delineation replaces fixed hydrology buffers

**Date:** 2026-07-03
**Status:** Accepted
**Owner:** Joshua Dell (solo)

## Context

The POC currently defines "riparian" as a fixed-width buffer around NHD flowlines
(`generate_buffers()`). This encodes a false assumption: that riparian extent is a constant
distance from a stream centerline. In the semi-arid San Juan Basin, riparian zones are
controlled by geomorphology + water-table access + actual phreatophyte vegetation
(cottonwood, willow — and invasive tamarisk / Russian olive), not distance. Many buffered
pixels are dry upland; many real riparian strips fall outside any fixed buffer. Every
downstream product (health score, compliance, the planned "unhealthy riparian" map) inherits
this error.

Pace et al. 2022 (*Ecological Indicators* 144:109519) compute NDVI only on "pure riparian
pixels" identified from a land-cover map precisely to avoid mixed-pixel noise — i.e. their
method is delineation-first. Applied RS practice (RF/XGBoost on multitemporal features + HAND
+ distance-to-channel; STAC datacubes) is the standard for this class of problem.

## Decision

Replace fixed-buffer delineation with a **learned, multi-evidence riparian extent map**:

- **Weak-supervision labels** from the agreement of three maps we already ingest — LANDFIRE
  EVT riparian classes ∧ NLCD woody/emergent wetlands ∧ NWI wetlands.
- **Features / evidence:** multitemporal Sentinel-2 index stats (NDVI/EVI/SWIR-moisture),
  GLCM texture, Sentinel-1 backscatter, and terrain (elevation, slope, **HAND**,
  distance-to-channel) derived from the 3DEP DEM.
- **Two methods, head to head:** RF/XGBoost on engineered features (baseline) vs. OlmoEarth
  multimodal embeddings (foundation model).
- **STAC datacube ETL:** `pystac-client` → `stackstac`/`odc-stac` → `xarray`, replacing manual
  per-scene pulls.
- **Validation** by spatial cross-validation (riparian data is spatially autocorrelated;
  random hold-out leaks) against a held-out reference map + NAIP visual spot-checks.

Scope: woody riparian condition + invasive detection. Output sequence: extent **map** →
condition **score** → **change** map. This ADR covers the extent-map stage (Stage 1).

## Alternatives considered

- **Keep fixed buffers, improve only the health score.** Rejected — the foundational error
  propagates regardless of how good the score is.
- **Take extent as given from LANDFIRE/NLCD/NWI directly (no learning).** Rejected as the
  primary method — those maps disagree, are coarse/dated, and give no confidence layer; but
  their *agreement* is exactly our weak-label signal, so they're retained as supervision.
- **UAV lidar/multispectral for fine-scale metrics.** Out of scope — no drone data. Airborne
  3DEP lidar covers the structural indicator.

## Consequences

- **Unlocks:** a defensible riparian map, a confidence/uncertainty layer, a baseline-vs-FM
  comparison (the portfolio's core ML story), and correct inputs for condition + change.
- **Costs:** `generate_buffers()` stops being the ETL foundation; a new `silver.riparian_extent`
  table replaces buffer-centric assumptions. `sql/create_schemas.sql` (a "Do Not Modify"
  file) needs a deliberate, reviewed revision — not an accident. New deps: `pystac-client`,
  `stackstac`/`odc-stac`, `xarray`, `scikit-learn`/`xgboost`, `olmoearth-pretrain-minimal`,
  `torch` (CPU). All require explicit sign-off per CLAUDE.md.
- **Risk:** "reliable" is bounded by weak-label quality and no field data. We state that
  ceiling explicitly rather than overclaim.
