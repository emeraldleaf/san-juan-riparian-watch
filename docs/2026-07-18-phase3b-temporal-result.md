# Phase 3B — the temporal gate: going back three years is essentially free (+0.003 AUC)

**Date:** 2026-07-18 · **Status:** second deep-time data point · reproducible via
[`phase3b_temporal.py`](../olmoearth_run_data/riparian_extent/phase3b_temporal.py) ·
spec: [Phase 3 — deep-time change](specs/2026-07-18-phase3-deeptime-change.md) ·
companion: [3A — the cross-sensor gate](2026-07-18-phase3a-cross-sensor-result.md)

## Why this gate exists

[3A](2026-07-18-phase3a-cross-sensor-result.md) proved a 2020-trained model survives the *sensor*
change (S2 → Landsat, **+0.046 AUC**). It said nothing about the *year*. 3B tests the axis that is the
whole point of a deep-time product: **does a model fit on 2020 imagery still rank riparian-vs-not in a
different year?** Ground truth for another year exists exactly once — the **CSU 2017 field points**.

## Method — isolating *time* from space and sensor

A naive "train on 2020, predict 2017" bundles four penalties into one uninterpretable number: sensor
(S2→Landsat), space (the training reach → the points), the beetle, and time. To isolate **time**, the
same RF (trained on the 2020 Sentinel-2 cube, riparian-vs-corridor pixels) is scored at the **same 167
points twice** — once on their **Landsat 2020** features, once on their **Landsat 2017** features:

- the **2020** score carries space + sensor,
- the **2017** score carries space + sensor **+ time**,
- their **difference is the temporal penalty** — space and sensor are common to both and cancel.

Ground truth: **167 CSU points inside the San Juan AOI** — 137 riparian-woody positives (tamarisk,
Russian olive, native, other woody) vs 30 non-riparian negatives (agriculture, absence, non-veg,
upland). Loaded through the tested `csu_points.py`, which corrects the `Virgin_River` trip's
transposed coordinates (20 of the 167) rather than trusting the raw `x`/`y`. Landsat is **point-sampled**
(6 bands × 12 months per point) because the points span ~150 km — far too wide for a dense cube.

## Result

| | AUC |
|---|---|
| Landsat **2020** @ points (space + sensor) | 0.698 |
| Landsat **2017** @ points (space + sensor + **time**) | 0.695 |
| **temporal penalty** | **+0.003** |

*167 points, 100 % sampled in both years. The two years' features are genuinely different (per-point
correlation 0.53, mean reflectance difference 0.054) — yet the model ranks the points equally well in
both. The near-identity is a result, not a caching artifact.*

## The decomposition — which axis actually costs anything

Reading 3A and 3B together, the deep-time penalties rank cleanly:

| Axis | Penalty | Where measured |
|---|---|---|
| **Time** (3-year gap) | **+0.003** | 3B (this) |
| **Sensor** (S2 → Landsat) | **+0.046** | 3A |
| **Space + label semantics** | **~0.20** | the absolute drop, 0.90 → 0.70 |

The absolute AUC at the points (~0.70) is well below 3A's cross-sensor 0.90 — **not because of time**,
but because this model was trained on **one reach** (Farmington) and asked to rank **basin-wide
occurrence points** whose label semantics differ from the extent polygons it learned on. That space +
label gap is the ~0.20, and it is the same for 2017 and 2020, so time is still cleanly isolated.

## Read it honestly

- **The penalty is the number; the absolute is confounded.** +0.003 isolates time; 0.70 reflects the
  one-reach-to-basin-wide-points transfer, not the year.
- **Label-semantics caveat.** The CSU points are *occurrence* points (a tamarisk in a field is a
  positive); the model learned *corridor extent*. This depresses the absolute AUC but affects both
  years equally.
- **Stability assumption.** Treating a 2017 label as valid for the 2020 prediction assumes woody
  presence is stable over three years at a point — reasonable for extent, and the thing that makes the
  difference-of-AUCs a temporal measurement.
- **2017 is beetle-era.** That the time penalty is ~0 also says defoliation did **not** hurt *extent*
  ranking — woody structure persists even when a tamarisk is defoliated. This is a mild positive for
  the extent side of the beetle worry; the *species* side is Phase 3C's problem, not 3B's.

## What it means for the deep-time product

Both model-agnostic axes are now **measured and cheap**: sensor +0.046, time +0.003. The deep-time
premise — an annual riparian product back into the Landsat era — **survives both gates**. The binding
constraint is not the year or the sensor but **spatial coverage of training**: a production model must
learn from more than one reach. That is a data-collection problem, not an architecture one — so it
does **not**, on this evidence, reopen the RF-vs-FM decision.

## Reproduce

```
# 1) build the 2020 S2 training cube (3A):
PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/phase3a_cross_sensor.py \
    --gdb <path>/GRSJ_Version2_0Plus_North.gdb
# 2) run the temporal gate (downloads the CSU points, samples Landsat 2017 + 2020 at them):
PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/phase3b_temporal.py \
    --gdb <path>/GRSJ_Version2_0Plus_North.gdb
```

Both years are cached per-run — but a year with a transient STAC failure is **not** cached, so a rerun
re-samples the timed-out months rather than reusing a partial cube.
