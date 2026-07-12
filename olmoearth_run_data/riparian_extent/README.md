# Riparian extent — OlmoEarth fine-tune (scaffold)

> ## This is STEP 1 of 2, and it is a **control** — not the deliverable
>
> Extent is already solved: CO-RIP mapped the whole Colorado Basin, San Juan included, at
> κ 0.80. Shipping only this reproduces published work. Its job here is to answer one narrow
> question — **does our fine-tuning pipeline work at all?** — before we spend a GPU on the task
> we actually care about (**Step 2: Tamarix vs native**, where no wall-to-wall map exists and
> phenology is the discriminator).
>
> Without this control, a bad invasives number is uninterpretable: broken pipeline, too few
> labels, and the *Diorhabda* beetle confound all predict the same failure. That is exactly the
> trap the first OlmoEarth attempt fell into.
>
> **Compare the result against the PIXEL-level RF baseline (spatial-CV F1 0.90–0.92)** — *not*
> the 0.701 patch-level number in `docs/olmoearth-vs-rf-baseline.md`, which belongs to the
> frozen-embedding + RF-head experiment. `SegmentationPoolingDecoder` predicts at pixel/segment
> level; scoring it against 0.701 would flatter it by ~0.2 F1 and manufacture a win.
>
> **Gate:** if extent lands well below 0.90, **stop and debug** — do not proceed to Step 2.
>
> Full rationale + decision table:
> [`docs/decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md`](../../docs/decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md) · tracked in issue #9.

Configs in the [`allenai/olmoearth_projects`](https://github.com/allenai/olmoearth_projects)
shape, so they can be dropped into an `olmoearth_projects` checkout at
`olmoearth_run_data/riparian_extent/` and run with `rslearn` + `olmoearth_run`.

Modelled on their **`mangrove`** project, which is the closest published analog to Stage 1:
segment a woody vegetation class near water from a Sentinel-2 time series, validated against
an authoritative reference map (Global Mangrove Watch there, **NMRipMap** here).

## Why this exists — the method gap

Our first foundation-model attempt (`python-etl/riparian/delineation/olmoearth.py`) reported
**RF F1 0.73 vs OlmoEarth-Nano F1 0.46** and concluded "the baseline won". Comparing against
Ai2's own recipe, that conclusion is probably measuring our *harness*, not the model:

| | Ai2 `mangrove` recipe | our `olmoearth.py` run |
|---|---|---|
| Checkpoint | `OLMOEARTH_V1_BASE` | Nano (smallest) |
| Backbone | **fine-tuned** (`FreezeUnfreeze`, unfreeze @ epoch 20, 10× LR) | **frozen** |
| Head | `SegmentationPoolingDecoder` + `SegmentationHead` | sklearn **RandomForest** on pooled tokens |
| Time series | **12 monthly S2 mosaics** (`period_duration: 30d`, `min_matches: 12`) | `max_timesteps=5` |
| Pooling | decoder consumes patch tokens | **mean-pooled over time AND band-sets** |
| Reported | 97.6% overall accuracy (mangrove) | F1 0.46 |

Mean-pooling over the time axis discards the phenology signal — the exact discriminator for
semi-arid riparian phreatophytes (green into the dry season because their roots reach
groundwater, while uplands brown out). So the FM was denied the thing it exists to exploit.

**Hypothesis to test:** a fine-tuned `OLMOEARTH_V1_BASE` over 12 monthly mosaics beats the
RF baseline (spatial-CV F1 0.90–0.92 on the NMRipMap-trained tiles). Confirm or refute — either
result is publishable; the current one is not a fair test.

## Labels — NMRipMap

`label` is a **vector** layer; `rslearn` rasterizes it to `label_raster` (band `label`, INT32).

Classes (`zero_is_invalid: true`, so 0 = no label / masked out):

| value | class |
|---|---|
| 1 | riparian |
| 2 | water |
| 3 | other |

Build the label vector from the sources we already have:
- **riparian (1)** — NMRipMap mapped-riparian polygons. We already fetch these:
  `python-etl/riparian/validation/reference.py::fetch_nmripmap` (paginated ArcGIS MapServer query).
- **water (2)** — NHD waterbodies / flowline buffers (`bronze.streams`, `bronze.waterbodies`),
  or the ESA WorldCover water class.
- **other (3)** — everything else inside the AOI that is neither, sampled to balance.

Coverage caveat: NMRipMap is **New Mexico only**, so the labelled AOI is the NM tiles
(Animas, Malpais). Turkey Creek (CO) has no reference map — it needs CO-RIP before it can
be trained or fairly evaluated. Do not train on weak labels here; that was the failure mode
that produced ~0.00 F1 on the Animas ag-valley tile.

## Split — spatial, not random

`train_config` / `val_config` select by `tags.split` within the `san_juan_nmripmap` group.
Tag windows by **spatially hashing their grid cell** (mangrove hashes 2×2 pixel cells), never
a random split — Sentinel-2 pixels are strongly autocorrelated and a random split leaks
near-duplicate neighbours into validation. This is the same discipline as
`python-etl/riparian/delineation/validate.py` (`assign_spatial_folds`, ~2 km blocks).

## Files

| file | purpose |
|---|---|
| `dataset.json` | rslearn dataset: S2 L2A (12 bands) as **12 monthly mosaics** over 366d, `label` vector, `output` raster |
| `model.yaml` | `OLMOEARTH_V1_BASE` + `SegmentationPoolingDecoder` (768→4), `FreezeUnfreeze` @20 / 10× LR, per-class precision/recall |
| `olmoearth_run.yaml` | `GridPartitioner` windows, `CombineGeotiff` postprocess, class colours |

## Running

Requires an `olmoearth_projects` checkout (Python 3.12 + `uv sync`) and a GPU — the earlier
CPU/Nano constraint is what forced the frozen-embedding shortcut. Note **OlmoEarth v1.1 cuts
compute ~3×** (Sentinel-2 bands merged into single tokens → 3× fewer tokens) and **v1.2 adds
RoPE**, so re-check whether a smaller variant is now viable before renting a GPU.

Env vars referenced by the configs: `DATASET_PATH`, `NUM_WORKERS`, `CHECKPOINT_PATH`,
`PREDICTION_OUTPUT_LAYER`, `WANDB_PROJECT` / `WANDB_NAME` / `WANDB_ENTITY`.

Inference writes GeoTIFFs; load them into `silver.riparian_extent` with
`method='olmoearth'` (the CHECK constraint already allows it) so the map's method toggle and
the RF-vs-FM disagreement analysis work unchanged.

## Status

**Scaffold only — not yet run.** These configs are transcribed from the published `mangrove`
project and adapted; the `rslearn` class paths are copied verbatim from it, but they have not
been executed against an `olmoearth_projects` checkout. Validate before trusting.
