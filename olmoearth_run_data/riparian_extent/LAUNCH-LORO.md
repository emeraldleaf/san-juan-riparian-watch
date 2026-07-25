# LORO fine-tune runbook — the FM-vs-RF deploy test

Score OlmoEarth **leave-one-reach-out** over the 4 diverse reaches the RF bar was measured on
(spec: `docs/specs/2026-07-19-fm-vs-rf-deploy-decision.md`). For each held-out reach the model trains
on the other three and predicts the held-out one; its **val riparian AUC is the transfer number**,
compared head-to-head with the RF bar:

| held-out reach | RF median-mosaic AUC (#71) |
|---|---|
| Farmington | 0.905 |
| Aztec/Animas | 0.886 |
| Kirtland | 0.845 |
| **Malpais (arroyo)** | **0.557** ← the sharp test |
| macro-mean | 0.798 |

**GO/ABORT** is the contract in spec #70 (arroyo +0.04 significant, or macro +0.04; coherence tie-break).

## Prerequisites

- The **4 per-reach datasets** built + materialized (`materialize_reach.py`): `dataset` (Farmington),
  `dataset_malpais`, `dataset_kirtland`, `dataset_aztec_animas`. ~53 GB total on the data drive.
- The `.venv-olmoearth` stack (`olmoearth-runner==0.1.14`, torch, rslearn). See `LAUNCH.md`.
- A **CUDA GPU** for the fits (RunPod L4/A10G ≈ $0.34–0.43/hr; ~2–7 GPU-h each → **~$3–15** total).
  Everything before the fit is CPU/local.

## Step 0 — validate on CPU first (no GPU)  ✅ done 2026-07-25

The Phase-0 discipline: prove the wiring on a laptop before renting. Already run and green
(1 clean NANO epoch, `val_loss` finite/decreasing) — reproduce if the datasets change:

```bash
cd olmoearth_run_data/riparian_extent
export PYTHONPATH=../../python-etl

# 1. Combine the 4 reaches into ONE dataset (hardlinks — ~no extra disk), tagged by reach.
python build_loro_dataset.py --dest dataset_loro          # -> 1404 windows, labels rasterized, verified

# 2. Set one fold (e.g. hold out Malpais) — flips options.split train/val by reach.
python run_loro.py --dest dataset_loro --hold-out malpais # (no --fit: sets split, prints the fit cmd)

# 3. NANO/CPU smoke test on that fold. NOTE the group fix:
python make_dryrun_config.py dataset_loro dryrun_loro.yaml --epochs 1
#   make_dryrun forces groups=[train]; the combined dataset uses group `san_juan_nmripmap`
#   (what model.yaml selects). Fix the 3 split configs before running:
sed -i '' 's/^\(        \)- train$/\1- san_juan_nmripmap/' dryrun_loro.yaml
python -m rslearn.main model fit --config dryrun_loro.yaml # expect 1 clean epoch, finite val_loss
```

## Step 1 — the GPU run (per fold)

On the GPU box, with the datasets present (rebuild via `materialize_reach.py` — the tool is cheap and
avoids a 53 GB upload — then `build_loro_dataset.py`). The real fits use `model.yaml` directly
(group `san_juan_nmripmap` — **no override needed**, unlike the dry-run):

```bash
export PYTHONPATH=../../python-etl
export WANDB_PROJECT=riparian-loro WANDB_ENTITY=<you> WANDB_NAME=fold-malpais   # optional
export NUM_WORKERS=8

for reach in farmington aztec_animas kirtland malpais; do
  WANDB_NAME=fold-$reach CHECKPOINT_PATH=.tmp/loro/$reach \
    python run_loro.py --dest dataset_loro --hold-out $reach --fit
done
```

`run_loro.py --fit` sets the fold's split then launches `rslearn model fit --config model.yaml`. Because
`val_config` selects `tags: {split: val}`, the **held-out reach is the validation set** — so the logged
`val riparian AUC` (WandB, or the CSV logger) **is** that fold's transfer AUC.

## Step 2 — score

Collect the best `val riparian AUC` per fold and lay it beside the RF column above. Apply the spec #70
contract: FM clears if the **arroyo fold** improves ≥ +0.04 (≥ 0.597) significantly with no other fold
regressing > 0.01, **or** the macro-mean improves ≥ +0.04 (≥ 0.838) significantly. Also compare
coherence (speckle/connectivity/Moran's I) at matched 0.80 recall. **Ship the winner; record the number
either way.**

## Notes / gotchas

- **Group name.** Local reach datasets use group `train`; the combined LORO dataset and `model.yaml` use
  `san_juan_nmripmap`. Only `make_dryrun_config.py` forces `train` (Step 0's `sed` fixes it).
- **Hardlinks.** `build_loro_dataset.py` hardlinks GeoTIFFs (same filesystem), so the combined dataset
  costs ~no extra space; only per-window `metadata.json` is written fresh (group + `reach` tag).
- **Same footing as the RF bar.** The reach bboxes match `deploy_extent_map.py`, and all four were
  materialized with identical 12-month median-mosaic compositing — the comparison is apples-to-apples.
