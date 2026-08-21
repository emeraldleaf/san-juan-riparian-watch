# ADR: basin-scale productionization — wall-to-wall riparian + invasive, annually

**2026-08-21 · status: proposed** · supersedes nothing; depends on the Stage-2 invasive
gate ([invasive FM-vs-RF LORO](../specs/2026-08-21-invasive-fm-vs-rf-loro.md)) for the
invasive product.

## Context

The experiment maps four reaches. The **product** is the whole San Juan basin (HUC8 `14080101`
today; the full San Juan watershed, ~99,000 km², as the ceiling), **every year**, for two layers:
riparian **extent** (Stage 1) and **native-vs-invasive** cover (Stage 2), with annual **change**
(Stage 3). That is a large-scale, recurring EO pipeline — the kind USGS, state agencies, and EO
companies actually run — and it has to be designed, not scaled up by accident.

The [FM-vs-RF result](../2026-08-01-fm-vs-rf-loro-result.md) settled the Stage-1 model: **OlmoEarth
is the basin model** because it holds on out-of-distribution ground where the pixel-wise RF collapses,
and the unlabeled basin is out-of-distribution ground you cannot hand-check. That is *why* this ADR
commits GPU inference to the basin rather than the cheap RF.

## Decision

1. **Classify the water's edge, not the basin.** The AOI is a **buffer around the NHD hydrography**
   (perennial + intermittent flowlines + waterbodies), not the full basin polygon. Riparian only
   exists near water, so a ~500 m–1 km buffer is a thin ribbon — a few percent of basin area — cutting
   the pixel count and GPU cost by 1–2 orders of magnitude. This is also on-thesis: we *learn* where
   riparian is inside the search zone, we do not assume the buffer is the answer.
2. **Tile the AOI and drive it from a `(tile, year)` manifest.** Every unit of work is one tile-year,
   tracked with a status so the basin is **resumable** — a failed tile re-runs alone, never the basin.
3. **Stream imagery, don't hoard it.** Per tile-year, build the 12-month S2 median cube by STAC index +
   **COG range-reads**, composite, infer, **discard the raw**. Store only compact outputs.
4. **Two-stage GPU inference.** Stage 1 extent → OlmoEarth; Stage 2 invasive → the invasive model
   **iff it clears its pre-registered LORO**. Per-tile probability rasters → mosaic → PostGIS medallion
   → MVT tiles. Stage 3 diffs year N against N-1 and the Landsat baseline.
5. **Run it on a batch orchestrator with spot GPU** (Azure Batch / Azure ML — we are already `azd`),
   scheduled annually after the growing season.

## The `(tile, year)` manifest

The spine of the whole system — one row per unit of work, the resumability contract.

| column | meaning |
|---|---|
| `tile_id` | stable id of the AOI tile (e.g. `h14080101_t0042`) |
| `year` | processing year |
| `bbox` | tile bounds (EPSG:4269) |
| `stage` | `cube` → `extent` → `invasive` → `mosaic` → `written` (furthest completed) |
| `status` | `pending` / `running` / `done` / `failed` |
| `cube_uri` | cached composite location (nullable; may be evicted after inference) |
| `extent_uri`, `invasive_uri` | output raster locations |
| `n_scenes`, `cloud_frac` | provenance: how much imagery backed the composite |
| `confidence` | tile-level mean prediction confidence (validation-at-scale signal) |
| `started_at`, `finished_at`, `gpu_seconds`, `cost_usd` | the cost model's raw data |

`gpu_seconds` and `cost_usd` per tile are not bookkeeping — they *are* the scaling estimate:
`Σ over one HUC10 × (basin tiles / HUC10 tiles)` is the honest basin cost before a dollar is committed.

## The per-tile loop (streaming inference)

```
for (tile, year) in manifest.where(status != done):
    cube   = materialize_cube(tile.bbox, year)     # STAC + COG range-reads → 12 monthly medians
    extent = olmoearth.predict_extent(cube)         # GPU; prob raster
    inv    = invasive_model.predict(cube, extent)   # GPU; only within extent  (Stage 2, gated)
    write_geotiff(extent, inv, tile.outputs)
    manifest.mark(tile, year, done, gpu_seconds, cost)
    del cube                                         # discard raw — storage stays GB, not TB
# after all tiles for the year:
mosaic → threshold → polygons + invasive share → PostGIS(silver/gold) → MVT tiles
change = diff(year, year-1, landsat_baseline)        # Stage 3
```

Reuses, generalized from the reach experiment: `materialize_reach.py` (the cube),
`deploy_extent_map.py` (inference + GeoJSON export — swap RF→FM), `riparian/reaches/processor.py`
(per-reach product), the medallion schema, MVT serving, `scheduler.py` + `entrypoint.py --mode
scheduled` (the annual hook). **What is new is the buffer-AOI, the tile manifest, and the batch
orchestration around them.**

## Cost model (parametric, to be filled by the HUC10 proof)

Let `A` = buffered-corridor area, `p` = pixels/km² at 10 m (~10⁴×10⁴/km² ... i.e. 10⁴ per km² per
band-month; the real driver is tiles × months × model FLOPs), `t` = GPU-seconds/tile (measured),
`g` = $/GPU-hour (spot). Then **basin-year cost ≈ (tiles) × t × g / 3600**, and the **HUC10 proof
measures `t` directly**. The dominant levers, in order: (1) buffer width (area), (2) spot vs on-demand
GPU, (3) months composited (12 for phenology vs fewer), (4) S2 vs Landsat resolution. Storage is
minor because raw is streamed, not kept.

## Validation at scale

You cannot hand-check a basin. The strategy is layered:
- **Transfer scores as the generalization warrant** — the LORO is *why* we trust the FM on unseen tiles.
- **Per-tile confidence** in the manifest — low-confidence tiles are flagged **provisional**, not silently shipped.
- **Spot-checks against reference** where labels exist (NMRipMap in NM, CO-RIP in CO).
- **The spatial-provenance gate** ([check-layer-colocation](../2026-08-21-reach-provenance-gap.md)) still
  applies — no published layer whose data/labels/imagery/score/map disagree on the ground.

Honest limit: the FM's OOD robustness is measured on **4 reaches**. The basin holds conditions outside
them, so monitoring + spot-validation is the safety net, not a formality.

## Alternatives considered

- **Dense whole-basin classification.** Rejected: 1–2 orders of magnitude more pixels for ~no gain —
  riparian is a corridor phenomenon; classifying upland desert is wasted GPU.
- **Google Earth Engine.** Viable for the compositing, but the FM fine-tune/inference lives off-GEE
  (PyTorch/GPU); keeping one stack (STAC + our inference) avoids a two-system seam. Revisit if
  compositing dominates cost.
- **Per-reach only (no wall-to-wall).** Rejected: the product thesis is *wall-to-wall*; per-reach is
  the experiment, not the deliverable.
- **RF for the basin (cheap, GPU-free).** Rejected for the reason the LORO exists: RF collapses on
  OOD reaches you can't flag in advance. RF stays a **fallback / cross-check**, not the basin product.

## Consequences

- Recurring GPU cost, bounded by the buffer-AOI and spot pricing; the HUC10 proof makes it a known number.
- An operational surface (a scheduled batch job with a manifest) to run and monitor annually.
- A defensible, honest product: provisional where confidence is low, validated where labels exist.

## First step

Prove the pipeline **end-to-end on one HUC10** (a handful of tiles): buffer → tile → cube → FM extent →
mosaic → PostGIS → MVT, resumable via the manifest, and capture **`t` (GPU-sec/tile) and `cost_usd`**.
That single number scales to the basin estimate and de-risks the whole project before any large commit.
Stage 2 (invasive) joins the loop **only after** its LORO gate is green.

See also: [FM-vs-RF LORO result](../2026-08-01-fm-vs-rf-loro-result.md) ·
[invasive LORO spec](../specs/2026-08-21-invasive-fm-vs-rf-loro.md) ·
[reach-cube materialization](../2026-07-18-reach-cube-materialization.md) ·
[reach-provenance gap](../2026-08-21-reach-provenance-gap.md).
