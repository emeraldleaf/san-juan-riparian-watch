# Technique — phenologically-aligned Sentinel-2 cubes, per reach, from scratch

**What this is:** the method for turning a bare bounding box into an analysis-ready
Sentinel-2 **time-series data cube** for a river reach — one that is directly comparable,
month-for-month and pixel-for-pixel, to every other reach built the same way. That
cross-reach comparability is not a nicety; it is the difference between a valid transfer
experiment and a garbage one. We learned that empirically, and the receipt is at the bottom.

**Diagram:** [`malpais-download-pipeline.svg`](malpais-download-pipeline.svg) draws the whole flow.
**Code:** [`olmoearth_run_data/riparian_extent/materialize_reach.py`](../olmoearth_run_data/riparian_extent/materialize_reach.py) — one command, any reach.

---

## The problem this solves

Riparian vegetation in the arid Southwest is **deciduous and phenology-driven**. Cottonwood,
willow, tamarisk and Russian olive all leaf out in spring and senesce in autumn — but on
*different schedules*, and that schedule difference (tamarisk leafs out and browns later, with a
distinct shortwave-infrared water signature) is the signal that separates native from invasive.

Two consequences follow, and both are traps:

1. **A single date tells you almost nothing.** One June scene captures one phenological moment.
   The discriminating signal lives in the *trajectory* across the season, so you need a **time
   series**, not a snapshot.
2. **The time series must be composited *identically* across areas you want to compare.** If reach
   A is built from 30-day median mosaics and reach B from single least-cloudy scenes, "June" means
   different leaf-out states in each. A model trained on A then sees B's features as out-of-
   distribution and fails — not because the biology differs, but because the *compositing* does.

So the technique is: **build every reach as the same phenological time-series cube.**

---

## The recipe, from scratch

Assume nothing but a bounding box (EPSG:4326) and a source of riparian polygons. Six steps.

### 0. Inputs
- **AOI:** `(minlon, minlat, maxlon, maxlat)`.
- **Label source:** riparian polygons with a species/class attribute. Ours is **NMRipMap** (a
  photo-interpreted vegetation map); the code reads it through a swappable `LabeledPolygonReader`
  Protocol, so CO-RIP or field points drop in without touching the rest.

### 1. Label-driven windowing — *don't download what teaches nothing*
Tile the AOI into fixed **32×32-pixel windows** in the local UTM zone at **10 m** (Sentinel-2
native). For each candidate window, intersect it with the (projected) label polygons and count
**positive pixels**, not positive polygons. Keep the window only if it contains riparian label;
drop pure-negative windows. On Malpais this kept **328 windows and skipped 1,822** — each skip is a
full multi-band, multi-month S2 download avoided. Windowing *before* fetching is the single biggest
efficiency lever.

### 2. Index the imagery via STAC
Query the **Planetary Computer STAC API** for the `sentinel-2-l2a` collection intersecting the AOI
over the target year. STAC returns an *index* of scenes (items) with per-band asset URLs pointing at
**Cloud-Optimized GeoTIFFs (COGs)** on Azure Blob — not the pixels yet, just the catalog.

### 3. Composite phenologically — *the load-bearing choice*
Configure the S2 source as **12 monthly median mosaics over a 366-day window**:
`period_duration: 30d`, `min_matches/max_matches: 12`, `space_mode: PER_PERIOD_MOSAIC`,
`harmonize: true`. Each of the 12 output "bands-in-time" is the **per-pixel median** of the clear
observations in its 30-day period — which suppresses residual cloud/shadow and, crucially, yields a
**stable, reproducible phenological trajectory** that is identical in construction for every reach.
`harmonize` puts pre- and post-2022 processing baselines on one radiometric scale. This step is the
whole reason the cubes are comparable.

### 4. Stream only the pixels you need
For each window × band × period, open the remote COG and read **only the byte ranges covering the
window** via HTTP range requests (`rasterio`/GDAL over `/vsicurl/`, asset URLs signed by
`planetary_computer.sign_inplace`). A Sentinel-2 scene is ~110 × 110 km; a window is 320 m. COGs
let you fetch the 32×32 footprint and discard the rest — **minutes, not hours, and megabytes, not
hundreds of gigabytes.** This is what makes local materialization tractable at all.

### 5. Materialize to per-window rasters, then **verify**
`ingest` writes the streamed granules to a tile store; `materialize` clips that store into the final
per-window GeoTIFFs (12 months × 12 bands each). Then **assert the rasters are on disk** —
`materialize` exits 0 even when every window failed (we hit exactly that when a config flag put it on
the direct-materialize path). `verify_materialized()` walks the windows and fails loudly if imagery
is missing. **Never trust the exit code.**

### 6. Concurrency + disk hygiene
- **`--workers N`:** ingest/materialize are **I/O-bound** (hundreds of independent COG reads), so
  parallel workers saturate the available bandwidth. We use 8 on an 8-core laptop.
- **Redirect temp:** `ingest` stages through `TMPDIR`; `materialize` uses GDAL's own `CPL_TMPDIR`.
  Both default to the boot volume and *will* fill it (they filled ours to zero once). Point
  `TMPDIR`, `TMP`, `TEMP` **and** `CPL_TMPDIR` at scratch on the data drive, and cap `GDAL_CACHEMAX`.
  Setting only one is the trap.

Output: `dataset/windows/<group>/<window>/layers/…` — 328 windows × 12 months × 12 bands. The tile
store (~11 GB) is intermediate and disposable; the materialized windows (~150 MB) are what training
and inference read.

---

## Why each choice is the right one (the design rationale)

| Choice | Why, specifically |
|---|---|
| 10 m Sentinel-2, not 30 m Landsat | The riparian corridor is ~8 px wide at 10 m but ~3 px at 30 m, where it blurs into irrigated agriculture — the exact native-vs-invasive confound. |
| 12 monthly **median** mosaics | Captures the leaf-out→senescence trajectory (the species discriminator) while medians reject residual cloud/shadow; identical construction ⇒ cross-reach comparability. |
| Label-driven window pruning | Avoids downloading pure-negative windows — the dominant cost. |
| COG range-reads | Turns "download 100 GB of scenes" into "stream the 320 m footprint." |
| `verify_materialized()` | `materialize` reports success on total failure; a green exit that means "nothing happened" is the most expensive kind of green. |
| Swappable label reader (Protocol) | The label source (GDB / live ArcGIS / CO-RIP / field points) is the one thing that varies by region; isolating it behind a Protocol makes the pipeline region-portable. |

---

## Is this current and pragmatic?

**The method is current; the tool choice is deliberate, and the alternatives are worth knowing.**

- **The techniques** — STAC indexing, COG range-reads, phenological median compositing, label-driven
  windowing, verify-don't-trust — are how modern EO/ML data pipelines are built in 2026. Nothing here
  is legacy.
- **The portable core is STAC + `odc-stac`/`stackstac` + xarray/dask.** That stack builds the same
  cube lazily as a chunked xarray, scales from a laptop to a dask cluster, and is vendor-neutral. It
  is the natural choice for a general-purpose cube builder.
- **We used `rslearn`** (Ai2's ML-dataset builder) because it materializes windows in exactly the
  shape our OlmoEarth fine-tune consumes — a good **ML adapter**, but it couples to Ai2's ecosystem,
  so it is not the general-purpose choice.
- **Google Earth Engine** is the dominant server-side alternative — no local download — at the cost of
  vendor lock-in and egress. The reason to prefer local materialization here: control over the exact
  preprocessing, no lock-in, and reproducible local artifacts.

**In short:** STAC-indexed, COG-streamed Sentinel-2 cubes with reproducible phenological compositing —
portable across cloud (dask) or laptop, with the imagery pipeline decoupled from the model.

---

## Reusability

`materialize_reach.py` is the pipeline as one command, parameterized by reach or bbox:

```bash
# a named reach from a local GDB
python materialize_reach.py --reach malpais --gdb NMRipMap.gdb --dest dataset_malpais --workers 8

# an arbitrary AOI (EPSG:4326)
python materialize_reach.py --bbox -108.82 36.81 -108.67 36.95 --gdb NMRipMap.gdb --dest dataset_x

# labelled windows only, skip the download (smoke test)
python materialize_reach.py --reach malpais --gdb ... --dest /tmp/d --skip-download
```

- **Any AOI:** `rslearn_dataset.build(bbox, …)` is fully bbox-parameterized.
- **Any label source:** swap the `LabeledPolygonReader` — GDB, live ArcGIS, CO-RIP, field points.
- **Coverage limit (be honest):** NMRipMap is **New Mexico only**. Colorado/Utah reaches need a
  different reader; the Protocol is the seam, but those readers aren't all built yet.

---

## The receipt — why this technique isn't optional

We tried to skip the proper materialize and cheaply fetch Malpais as **one least-cloudy scene per
month**. Trained on Farmington's 30-day median mosaics, the RF transfer to that cheap Malpais cube
scored **AUC 0.371 — worse than random**: the features were sampled at different phenological moments,
so they were out-of-distribution. Rebuilding Malpais with the *identical* 12-month median compositing
is what makes the transfer number mean anything. **Aligned phenological compositing is the
experiment**, not a preprocessing detail — which is exactly why it earns its own document.
