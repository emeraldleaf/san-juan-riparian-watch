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
| Model | **`OLMOEARTH_V1_1_BASE`** — 207.5 M params (weights+grads+Adam ≈ **3.3 GB** fp32) |
| Tokens/window | **3,072** on v1.1 — vs **9,216 on v1**. Measured, see below. |
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

## 🔴 Use v1.1-Base, not v1-Base — the scaffold is wrong

`model.yaml` still says `OLMOEARTH_V1_BASE`. **Measured** on the actual config (32×32 window, 12
monthly mosaics, `patch_size: 2`):

| Checkpoint | Tokens/window |
|---|---|
| `OLMOEARTH_V1_BASE` | **9,216** |
| **`OLMOEARTH_V1_1_BASE`** | **3,072** — v1.1 merges the S2 bands into single tokens (band-set axis 3 → 1) |

**3× fewer tokens, and attention is O(n²), so it compounds.** Every cost figure above assumes v1.1;
on v1 the run is roughly 3× more expensive and **may not fit 24 GB at batch 8**. Our own fair test
found **v1.1 ≈ v1 in quality** (within noise), so this is free.

> ⚠️ **Phase-0 check:** Ai2's `mangrove` recipe uses `V1_BASE`, so **rslearn 0.0.27 may not wire the
> v1.1 model ID**. Verify it resolves *before* renting anything. If it does not: either patch the ID
> or accept 3× the cost — but decide it on the ground, not on the clock.

## 🎯 Two-stage supervision — use the out-of-AOI data. It is ~1000× our in-AOI supervision.

This is the single biggest lever in the plan, and the reason to be greedy about other people's data.

**The problem.** Supervision available *inside* the San Juan for the species task:

| In-AOI | |
|---|---|
| CSU field points | **167** |
| …of which beetle-defoliated | **0** |
| NMRipMap `IC` | 332 polygons — and it **conflates** tamarisk with Russian olive |

**The data we were about to ignore**, all Colorado Plateau, all CC BY-SA / CC0:

| Out-of-AOI (same ecoregion) | |
|---|---|
| **CSU tamarisk *probability* raster** — Dolores | **36,114 px** @30 m |
| **CSU tamarisk probability raster** — Green | **121,070 px** @30 m |
| CSU field points, Plateau pool | 1,096 records (**305 beetle-affected**) |
| CO-RIP riparian extent | basin-wide (incl. our AOI), millions of px — weak, 2–35 % OOB |

**The design: pre-train on abundant-and-weak, fine-tune on scarce-and-strong.**

| Stage | Labels | Imagery | Why |
|---|---|---|---|
| **A — auxiliary** | CO-RIP extent (2016) · CSU tamarisk probability, Dolores + Green (2016) | **S2 2016** | Learn the representation from ~1000× more supervision |
| **B — fine-tune** | NMRipMap (extent) · CSU field points (species, incl. defoliation) | **S2 2020** / **S2 2017** | Adapt to the real task on the labels we trust |
| **Validate** | held-out AOI windows | matching year | Report honestly, per ecoregion |

**This is also the FM's central claim, finally put to the test.** "Better accuracy from the same
scarce labels" is what a foundation model is *for*, and our literature review recorded it as
**untested** in this domain. Stage A→B is exactly that experiment: if the FM cannot convert abundant
weak supervision into in-AOI accuracy, that is a real finding about foundation models, not a shrug.

### The four guardrails — without these it is just noise

1. **Ecoregion-match the auxiliary data.** Colorado Plateau only. The beetle-pool ADR established that
   pooling across ecoregions imports domain shift; CO-RIP's own κ spans **0.42–0.90 across ecoregions**.
   Do not pour the Sonoran Desert into the loss because it is free.
2. **Confidence-weight the loss.** CO-RIP's OOB error is 2–35 % *by ecoregion* and it **over-predicts at
   high elevation** — `corip.py::ECOREGION_CONFIDENCE` already carries this (0.55 Southern Rockies,
   0.95 arid lowland). An unweighted weak label teaches the model that **upland is riparian**, which is
   the exact failure the NMRipMap crosswalk exists to prevent.
3. **Match each label source to its own year.** CO-RIP & the CSU raster are **2016** → S2 2016. NMRipMap
   is **2020** → S2 2020. CSU points are **2017** → S2 2017. Never mix a label with another year's
   reflectance; we have already made that mistake once.
4. **Mind the 30 m → 10 m boundary noise.** CO-RIP and the CSU raster are Landsat-derived; rasterised
   onto a 10 m grid, every class boundary is up to three pixels of nonsense. **Down-weight boundary
   pixels**, or run Stage A at 30 m and Stage B at 10 m.

### And the honest caveat

The CSU tamarisk raster is **Landsat-derived — and CSU themselves say Landsat cannot resolve the
tamarisk phenological signature** (*"without a different sensor with greater spectral or grain
resolution this is a difficult constraint to overcome"*). So Stage A teaches the model a **noisy,
sensor-limited** notion of tamarisk. That is fine for a *prior* and dangerous as a *target*: if Stage B
cannot pull away from it, we have merely learned to imitate the incumbent's limits. **Report the Stage-A
-only baseline alongside Stage A→B**, so the difference is visible rather than assumed.

## Phase 0 — local, free, and the entire risk

**Everything that can go wrong lives here.** Nothing is rented until Phase 0's exit gate passes.

1. **Install the stack** in a Python 3.11 venv (`olmoearth-runner==0.1.14`). Confirm
   `from olmoearth_run.partitioners.grid import GridPartitioner` imports.
2. **Build the label vector layer** — the real work.
   - *Control (extent):* NMRipMap → `1 = riparian, 2 = water, 3 = agriculture, 4 = other`,
     `zero_is_invalid: true`. **Four classes, not three** — this line said `3 = other` until the
     layer was built; the scaffold's `model.yaml` has said `num_classes: 4` all along, and the
     crosswalk splits agriculture from upland. Agriculture earns its own class because it is the
     one negative that is *as green as riparian*: fold it into "other" and NDVI can no longer
     separate the classes, which is exactly the failure the validator below is built to catch.
     Woody-riparian classes only (`riparian/labels/nmripmap.py` — **never a raw fetch**).
     Water from NHD/WorldCover. "Other" balanced by sampling, **clipped to the VBET valley bottom**
     (`riparian/delineation/vbet.py`) so the negatives are corridor negatives, not desert.
   - *Invasives:* CSU points → `tamarisk / russian_olive / native / other`, with **defoliation as a
     state** (`riparian/labels/csu_points.py`, `colorado_plateau()` pool).
   - Output: GeoJSON per window, in the CRS/shape `dataset.json`'s `label` layer expects.
   - Built by `riparian/labels/label_layer.py`. Two things there are load-bearing, both about the
     negatives: they are **clipped to the valley bottom** (a desert negative teaches "is it green",
     which is not the task) and **capped at 3× positive area** (unbalanced, a segmentation head
     reaches ~90% accuracy by predicting "other" everywhere while the loss curve looks *healthy*).
2b. **Validate the labels against the imagery — BEFORE renting anything**
   (`riparian/labels/validate_layer.py`). A label layer can be schema-perfect and still be wrong in
   the only way that matters: not lining up with the pixels. Nothing in `rslearn` will say so —
   training runs, loss falls, metrics look plausible, and you find out after you have paid.
   - **Separability.** Sample peak-season NDVI from **S2 2020** (the label's own vintage) and ask
     how well NDVI alone separates riparian from corridor negatives. `AUC < 0.65` → the labels are
     broken or misaligned, **stop**. `> 0.95` is *suspicious, not good*: if one hand-computed index
     nearly solves the task, the negatives are probably desert and the task is leaking.
   - **The shift test — the one separability cannot do.** Re-score with the labels translated ±3 px.
     **If a shifted version scores better, the labels correlate with the imagery but do not sit ON
     it.** Separability still passes; every trained metric is then quietly wrong. We have been
     burned by this one's cousin — the AUC-0.23 incident *looked* exactly like a misregistration
     and was an unshuffled CV split. A real one would look identical. Measure the offset; don't guess.
     (Tie-break toward zero shift: a straight reach is invariant along its own axis, so an arbitrary
     argmax invents a displacement and reports a bug in labels that are fine.)
   - **Eyes.** Overlay the polygons on **NAIP 2020** and look. NAIP 2020 is not a proxy for the
     truth — it *is* the imagery NMRipMap was photo-interpreted from. A metric tells you the labels
     are self-consistent; only your eyes tell you they are on the trees.
3. **Materialise the Sentinel-2 cube locally** (`rslearn dataset prepare|ingest|materialize`). This is
   **CPU + network**, ~1.2 GB. Do it here, not on a GPU clock — a GPU idling during a Planetary
   Computer download is money set on fire.
4. **Dry-run on `OLMOEARTH_V1_NANO`, MPS/CPU, 1 epoch, a handful of windows.**

> ### ✅ Phase-0 exit gate — do not rent a GPU until ALL of these hold
> - `olmoearth-runner` imports; the scaffold's class paths resolve.
> - **The label layer passes `validate_layer.report()`** — NDVI separability is not BROKEN, and the
>   shift test finds no offset that beats zero. This gate is deliberately hard: every failure it
>   catches is free here and expensive later.
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
