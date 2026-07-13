# Execution plan — the OlmoEarth fine-tune (issue #9)

**Status:** Ready to execute · **Depends on:** the
[fine-tune ADR](../decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md) and the
[beetle-pool ADR](../decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md) · See CLAUDE.md.

The *what* and the *why* are already decided. This is the *how*, costed, with the abort criteria
written **before** the money is spent.

## The headline: compute is not the constraint

| | |
|---|---|
| Control AOI (Animas + Malpais) | **428 km²** → 4.28 M px @ 10 m → **~4,180 windows** (32×32) |
| Sentinel-2 cube | 12 monthly mosaics × 12 bands × uint16 ≈ **1.2 GB** |
| Model | `OLMOEARTH_V1_BASE` — **207.5 M params** (weights+grads+Adam ≈ **3.3 GB** fp32) |
| Tokens/window | 3,072 (patch 2 · 16×16 patches · 12 dates) |
| VRAM | **24 GB is comfortable** (L4 / A10G). 16 GB workable at batch 4 + AMP. |
| Training | batch 8, 60 epochs ≈ 31 k steps → **2–5 GPU-hours** |
| **Cost of the control run** | **≈ $2–5** (RunPod L4 ≈ $0.43/hr, A10G ≈ $0.34/hr) |
| **Realistic total** incl. debugging, invasives, inference | **$30–60** |

**Spending $40 is not the risk. Spending three days debugging `rslearn` on a rented GPU is.** The plan
is built around that.

## The stack (verified, not assumed)

```
olmoearth-runner==0.1.14     # PyPI. Python >=3.11,<3.12 — we are on 3.11 ✓
  └── rslearn==0.0.27        # pinned by the runner; do NOT install rslearn latest (0.1.12)
```

The import name is `olmoearth_run`; the **PyPI package is `olmoearth-runner`**. There is no
`olmoearth_run` package and no `allenai/olmoearth_run` repo — our scaffold's class paths
(`olmoearth_run.partitioners.grid.GridPartitioner`) are correct, but the install line is not obvious,
and guessing it on a GPU clock would have cost real money. Ai2's own
[`olmoearth_projects/pyproject.toml`](https://github.com/allenai/olmoearth_projects) is the source of
truth.

---

## Phase 0 — local, free, and the entire risk

**Everything that can go wrong lives here.** Nothing is rented until Phase 0's exit gate passes.

1. **Install the stack** in a Python 3.11 venv (`olmoearth-runner==0.1.14`). Confirm
   `from olmoearth_run.partitioners.grid import GridPartitioner` imports.
2. **Build the label vector layer** — the real work.
   - *Control (extent):* NMRipMap → `1 = riparian, 2 = water, 3 = other`, `zero_is_invalid: true`.
     Woody-riparian classes only (`riparian/labels/nmripmap.py` — **never a raw fetch**).
     Water from NHD/WorldCover. "Other" balanced by sampling, **clipped to the VBET valley bottom**
     (`riparian/delineation/vbet.py`) so the negatives are corridor negatives, not desert.
   - *Invasives:* CSU points → `tamarisk / russian_olive / native / other`, with **defoliation as a
     state** (`riparian/labels/csu_points.py`, `colorado_plateau()` pool).
   - Output: GeoJSON per window, in the CRS/shape `dataset.json`'s `label` layer expects.
3. **Materialise the Sentinel-2 cube locally** (`rslearn dataset prepare|ingest|materialize`). This is
   **CPU + network**, ~1.2 GB. Do it here, not on a GPU clock — a GPU idling during a Planetary
   Computer download is money set on fire.
4. **Dry-run on `OLMOEARTH_V1_NANO`, MPS/CPU, 1 epoch, a handful of windows.**

> ### ✅ Phase-0 exit gate — do not rent a GPU until ALL of these hold
> - `olmoearth-runner` imports; the scaffold's class paths resolve.
> - The dataset materialises and `rslearn model fit` **completes one epoch without error**.
> - Loss is **finite and decreasing**. A NaN here is a normalisation bug, and it costs $0 to find now.
> - Predictions are **spatially aligned** with the labels (overlay them and look — the AUC-0.23
>   incident was a spatial-alignment scare that turned out to be an unshuffled CV split; a real
>   misalignment would look identical).

## Phase 1 — the extent control (GPU)

Per the ADR: `OLMOEARTH_V1_BASE`, `FreezeUnfreeze` (unfreeze @ epoch 20, 10× LR),
`SegmentationPoolingDecoder`, **12 monthly S2 mosaics**, spatial split.

- **AOI: Animas + Malpais only. Turkey Creek is HELD OUT** — its only reference is CO-RIP, which
  over-predicts in the Southern Rockies (confidence 0.55). A control fed weak, biased labels cannot
  do a control's one job.
- **Imagery: Sentinel-2 2020** — NMRipMap is NAIP-2020-derived. Fit on the label's year.
- **Compare against the PIXEL-level RF baseline: F1 0.90–0.92.** *Not* the 0.701 patch-level number —
  that belongs to the frozen-embedding experiment, and using it would flatter the model by ~0.2 F1.

> ### 🚦 GATE — if extent lands well below ~0.90 pixel F1: **STOP.**
> Do not proceed to invasives. A broken pipeline and a hard task produce the same bad number, and
> that ambiguity is the whole reason this control exists. Debug, then re-run.

## Phase 2 — invasives (GPU)

Same cube, same code path; swap the label layer.

- **Train on the ecoregion-matched Colorado Plateau pool** (Escalante + SouthWest_CO): 1,096 records,
  610 invasive, **305 beetle-affected** (117 defoliated / 145 mixed / 43 dead).
- **Imagery: Sentinel-2 2017** — the CSU points are a 2017 field season.
- **The San Juan is an OUT-OF-SAMPLE validation set, not a held-out split.** We are testing transfer
  across a prevalence gap (Escalante 21.6 % live tamarisk vs San Juan 74.1 %), and must say so.
- **Defoliation is a class, never an absence.** A defoliated stand is still *Tamarix*.

## Phase 3 — the contribution (mostly CPU)

Roll the calibrated model across the archive: **annual extent** and **annual native-vs-invasive
cover**. Inference is embarrassingly parallel and needs no training GPU — per the hosting ADR, this is
on-demand batch with **zero idle cost**.

Sensor choice is decided **after Phase 1, on evidence**: Sentinel-2 (10 m, 2016→) resolves the corridor
but misses the pre-beetle era; Landsat (30 m, 1984→) spans it but may be too coarse. **If the 10 m
control barely resolves the corridor, 30 m will not.**

---

## Risk register — the honest version

| Risk | Likelihood | Mitigation |
|---|---|---|
| **`rslearn` dataset build fights us** | **High** — we have never run it | It is Phase 0, it is free, and it is the exit gate. This is the plan's whole shape. |
| Label layer geometry/CRS mismatch | Medium | Overlay predictions on labels and *look*. Do not trust a metric to reveal a spatial bug. |
| 32×32 windows (320 m) too coarse for a narrow corridor | Medium | Corridors are 50–200 m; a window will contain riparian *and* upland. If recall collapses, try patch 1 / larger windows before blaming the model. |
| OOM on 16 GB | Low | Take 24 GB. The difference is ~$0.10/hr. |
| Beetle transfer fails (Escalante → San Juan) | **Medium-high, and interesting** | It is a *finding*, not a failure — pre-registered in the beetle-pool ADR. |
| Cost overrun | Low | Hard cap **$100**. At $0.43/hr that is 230 GPU-hours; the plan needs <15. |

## What we are NOT doing

- **No always-on GPU.** On-demand batch only (hosting ADR).
- **No Turkey Creek in the control.**
- **No blended AOI-wide accuracy number.** CO-RIP's κ spans 0.42–0.90 *across ecoregions*; a single
  number would hide exactly the effect we care about. **Report per region.**
- **No fitting a label source against the wrong year.** NMRipMap → 2020, CSU points → 2017, CO-RIP →
  2006/2016. `corip.label_from_pixel()` raises on an unmodelled year; this is enforced in code.

## Immediate next action

**Phase 0, step 2: build the label vector layer.** It is the critical path, it is free, and every
downstream phase is blocked on it.
