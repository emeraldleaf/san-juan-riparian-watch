# Phase 3A — the cross-sensor gate: RF's Sentinel-2 → Landsat penalty is small (+0.046 AUC)

**Date:** 2026-07-18 · **Status:** first 3A data point · reproducible via
[`phase3a_cross_sensor.py`](../olmoearth_run_data/riparian_extent/phase3a_cross_sensor.py) ·
spec: [Phase 3 — deep-time change](specs/2026-07-18-phase3-deeptime-change.md)

## Why this gate exists

The whole Phase-3 contribution is the **time axis** — annual riparian extent and native-vs-invasive
cover back into the Landsat era. Sentinel-2 (10 m, 2015→) is where the labels and the signal are;
**Landsat (30 m, 1984→) is the only sensor that reaches the pre-beetle baseline.** So the deep-time
product depends on a model fit on S2 *holding* on Landsat. Before committing to any archive
architecture — and before the RF-vs-FM decision, since multi-sensor pretraining is the foundation
model's one structural edge — 3A asks the narrow, decidable question: **at a single date where
ground truth exists, how much accuracy is lost purely to the sensor change?**

## Method — the same-pixel comparison that isolates the sensor

Both sensors were built on **one enforced footprint**: the same AOI (a Farmington sub-reach with
NMRipMap labels), reprojected to a single **10 m UTM grid**, restricted to the **6 shared bands**
(blue/green/red/NIR/SWIR-1/SWIR-2), **12 monthly composites** across 2020, each converted from its
own DN scaling to **surface reflectance (0–1)** so the values are comparable. Landsat's native 30 m
is resampled onto the 10 m grid — this *aligns* the grids without inventing detail, so the
resolution disadvantage is **preserved, not hidden**.

NMRipMap riparian labels were rasterised onto that grid (via the tested `label_layer` +
`validate_reach` path — never a raw fetch). A **Random Forest** (300 trees, balanced) was trained on
the **S2** side, then scored on the **same spatially-held-out pixels** twice — on their S2 features
and on their Landsat features. Train/test were split by a **spatial checkerboard** (64 px blocks) so
train and test pixels never coincide, and the *identical* split was used for both sensors.

## Result

| | AUC |
|---|---|
| in-sensor (train S2 → test S2) | **0.942** |
| cross-sensor (train S2 → test Landsat) | **0.896** |
| **sensor penalty** | **+0.046** |

*180,363 usable pixels (69,144 riparian / 111,219 corridor-negative); ~90 k train / ~89 k test.*

## Read it honestly

- **The penalty is the robust number, not the absolute AUCs.** The checkerboard split has adjacent
  train/test blocks, so spatial autocorrelation inflates *both* scores — 0.942 in-sensor is
  optimistic. But the penalty is measured on **identical pixels**, so that leakage affects both
  scores and largely cancels in the difference.
- **This isolates the sensor axis at one date only.** It does **not** settle deep time. Temporal
  drift (predict *other* years — Phase 3B) and the **beetle signal inversion** (Phase 3C) are
  separate, unsolved, and — critically — **model-agnostic**: no architecture invents pre-2017 labels
  or un-confounds defoliation. 3A moves exactly one of the three deep-time risks.
- **The resolution disadvantage is real, not resampled away.** Landsat pixels are 30 m native blurred
  onto the 10 m grid; the model sees genuinely coarser information and still ranks it well.

## What it means for RF vs the foundation model

On the **one axis where the foundation model has a structural edge** — multi-sensor pretraining — a
plain per-pixel RF trained on Sentinel-2 already crosses to Landsat for a **0.046 AUC give-up**.
That is consistent with the single-epoch finding that RF and the fine-tuned FM **tie** (see
[methods & metrics](2026-07-18-methods-and-metrics.md)): the FM's cross-sensor advantage is **not
decisive** here, and RF remains the pragmatic choice for the archive roll-out. The decision could
still reopen if **3B** (temporal transfer) shows a large drop that pretraining demonstrably closes —
but that is the next measured gate, not an assumption.

## Reproduce

```
PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/phase3a_cross_sensor.py \
    --gdb <path>/GRSJ_Version2_0Plus_North.gdb --dest .tmp/xsensor.npz
```

The fetch flags any month whose STAC search failed transiently (`search-failed=[...]`) and refuses
to save a poisoned cube, rather than letting an API timeout masquerade as a no-data month. (The
first run of this test *did* hit that trap — several S2 months came back empty from timeouts, not
absence of imagery; the hardened fetch makes the two distinguishable.)
