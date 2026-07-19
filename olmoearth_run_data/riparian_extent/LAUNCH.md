# Phase 1 launch kit — the extent control GPU run (issue #47)

> **The do-not-rent-a-GPU gate is GREEN.** Every laptop/$0 blocker is cleared: checkpoint
> resolved to `V1_BASE` (#44), per-pixel `UNetDecoder` wired + validated (#45), labels
> eye-checked as aligned on NAIP (#46), a second reach reproduced the separability
> (Malpais AUC 0.802, #51), and the FM premise survived its strongest published challenge
> (CropGlobe, #48). This file is the runbook for spending the GPU — **you** rent and run it;
> nothing here spends money on its own.

This is **STEP 1 of 2 and a control**, not the deliverable. Extent is already solved
(CO-RIP, κ 0.80). Its only job: prove the fine-tuning pipeline works *before* we spend a GPU on
the task we care about (Step 2, invasives). See [`README.md`](README.md) for the full rationale.

---

## 0. What is already verified (do not re-litigate)

| Thing | State | Where |
|---|---|---|
| `model.yaml` checkpoint | `OLMOEARTH_V1_BASE` | line 11 |
| Decoder | `UNetDecoder(in_channels=[[2, 768]], out_channels=5)` per-pixel | lines 15–21 |
| Classes | 5 (`zero_is_invalid` ⇒ 0 ignored + **4 real**: 1 riparian, 2 water, 3 agriculture, 4 other) | line 88 |
| Time series | 12 monthly S2-L2A mosaics, 12 bands | `dataset.json`, `model.yaml` inputs |
| Fine-tune schedule | `FreezeUnfreeze` unfreeze @ epoch 20, 10× LR | lines 328–335 |
| `rslearn model fit` runs clean | ✅ NANO dry-run, 3 epochs, val_loss ↓, per-pixel metrics non-degenerate | Phase-0 record |
| **Materialised cube on disk** | ✅ 11 GB tile store + materialised windows on the **data drive** | `dataset/` |

The cube is already built — **do NOT re-materialise on a GPU clock.** A GPU idling during a
Planetary Computer download is money set on fire. If the tile store was disturbed, re-materialise
**on the laptop** first (§2).

---

## 1. Pre-flight on the laptop — $0, do this BEFORE renting

```bash
# From repo root. These re-confirm the cube the model will train on is real and aligned.

# (a) The materialised cube is intact and honestly separable (water-excluded contract):
PYTHONPATH=python-etl \
  .venv-olmoearth/bin/python olmoearth_run_data/riparian_extent/validate_materialized.py \
  olmoearth_run_data/riparian_extent/dataset
#   Expect AUC ≈ 0.75 (peak-season, corridor-negative). If it errors or reads BROKEN, the tile
#   store is damaged — re-materialise (§2) before spending a cent.

# (b) Every scaffold class_path still resolves (the 5-broken-fiction check):
./dev.sh --check-encoding
```

If `dataset/tiles` is missing or `validate_materialized` fails, rebuild the cube locally with the
temp redirects (the disk-crisis fix — **both** escape to the boot disk if you set only one):

## 2. Re-materialise (only if the cube is gone) — $0, laptop

```bash
export TMPDIR="$PWD/.tmp" TMP="$PWD/.tmp" TEMP="$PWD/.tmp"   # Python/rslearn staging (ingest leak)
export CPL_TMPDIR="$PWD/.tmp"                                 # GDAL scratch (materialize leak)
export GDAL_CACHEMAX=256
mkdir -p .tmp
# Build via riparian/delineation/rslearn_dataset.py (ingest: true — direct-materialize raises
# NotImplementedError by design on Planetary Computer's Sentinel2). Then ALWAYS:
#   rslearn_dataset.verify_materialized()  — asserts rasters on disk; NEVER trust the exit code.
```
Budget **~15 GB** for the tile store (ours came to 11 GB). Materialised windows are ~1.2 GB.

---

## 3. Rent the GPU

- **24 GB card** (L4 or A10G). 16 GB risks OOM; 24 GB is ~$0.10/hr more — take it.
- RunPod L4 ≈ $0.43/hr · A10G ≈ $0.34/hr.
- **Hard cost cap: $100.** At $0.43/hr that is 230 GPU-hours; the plan needs **< 15**.
- Python 3.12 + `uv sync` against an [`olmoearth_projects`](https://github.com/allenai/olmoearth_projects)
  checkout (these configs drop into `olmoearth_run_data/riparian_extent/`). The PyPI package is
  **`olmoearth-runner`**; the import name is `olmoearth_run`.

Copy the materialised `dataset/` to the GPU box (or re-materialise there — but that burns GPU time
on a CPU/network task; prefer copying).

## 4. Env vars the configs reference

```bash
export DATASET_PATH=/path/to/olmoearth_run_data/riparian_extent/dataset
export NUM_WORKERS=8
export CHECKPOINT_PATH=/path/to/checkpoints/riparian_extent
export WANDB_PROJECT=san-juan-riparian   WANDB_NAME=extent-control-v1base   WANDB_ENTITY=<you>
export PREDICTION_OUTPUT_LAYER=output     # only needed for the predict step (§6)
```

## 5. Train

```bash
rslearn model fit --config olmoearth_run_data/riparian_extent/model.yaml
```
- `rslearn model fit` is the **verified** entry point (Phase-0 dry-run ran exactly this, NANO/CPU).
- ~60 epochs, batch 32 + AMP → **~2–7 GPU-hours** (V1_BASE's 3× attention cost widens this).
- Watch: `val_loss` decreasing, no NaN/inf. The encoder is **frozen until epoch 20**, then unfreezes
  at 10× LR — expect the train dynamics to shift there; that is the fine-tune, not a bug.
- `ModelCheckpoint` saves best-on-`val_loss` + last to `$CHECKPOINT_PATH`.

## 6. 🚦 GATE — score against the PIXEL-level RF baseline, then decide

- **Compare per-pixel F1 against RF's spatial-CV F1 0.90–0.92.** **NOT** the 0.701 patch-level
  number (that belongs to the frozen-embedding + RF-head experiment; using it flatters the FM by
  ~0.2 F1 and manufactures a win).
- **Report per region (Animas vs Malpais), never one blended number** — CO-RIP's κ spans 0.42–0.90
  across ecoregions; a single figure hides exactly the effect that matters.
- **Overlay predictions on the labels and LOOK.** The per-pixel decoder finally makes this
  meaningful (the pooling head could not). A metric will not reveal a spatial bug.

> ### If extent lands well below ~0.90 pixel F1: **STOP. Do not proceed to invasives.**
> A broken pipeline and a genuinely hard task produce the *same* bad number — that ambiguity is the
> whole reason this control exists. Debug (window size, label registration, class balance), re-run.
> Only a passing control makes a Step-2 invasives number interpretable.

## 7. Predict / inference — ⚠️ NOT yet executed end-to-end

```bash
# Windowing + postprocess config: olmoearth_run.yaml (GridPartitioner, CombineGeotiff).
# Prediction geometry start = 12 months BEFORE the target date (model eats a 12-month series).
# rslearn writes GeoTIFFs; load into silver.riparian_extent with method='olmoearth'
# (the CHECK constraint already allows it) so the map's method toggle + RF-vs-FM diff work unchanged.
```
The train path (`model fit`) is verified; the **predict/runner path has never been run** — treat the
first inference as its own small shakeout, not a trusted step.

---

## Cost summary

| | |
|---|---|
| Extent control run | **≈ $3–15** (L4/A10G, 2–7 GPU-hr) |
| Realistic total incl. debugging + invasives + inference | **$40–90** |
| **Hard cap** | **$100** |

**Spending $40 is not the risk. Spending three days debugging `rslearn` on a rented GPU is** — which
is why Phase 0 caught seven config bugs for $0. This kit exists so the GPU clock only ever runs the
things that genuinely need a GPU.

## Traps already paid for (don't re-pay)

- **Temp escapes to the boot disk** — set `TMPDIR`/`TMP`/`TEMP` **and** `CPL_TMPDIR`; fixing one
  leaves the other.
- **`materialize` exits 0 having written nothing** — always `verify_materialized()`, never the exit
  code.
- **`num_classes` is 5, not 4** — `zero_is_invalid` reserves class 0; pinned by
  `tests/test_class_scheme_contract.py`.
- **Fit only on the label's own year** — NMRipMap ⇒ S2 **2020**. Animas + Malpais only;
  **Turkey Creek is held out** (its only reference is CO-RIP, biased in the Southern Rockies).
