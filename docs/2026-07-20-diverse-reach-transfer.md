# The RF bar for the FM decision: diverse-reach pooling closes transfer — except the arroyo

**Date:** 2026-07-20 · **Status:** the honest baseline for the FM-vs-RF deploy decision (spec
`specs/2026-07-19-fm-vs-rf-deploy-decision.md`, PR #70) · reproducible via
[`deploy_extent_map.py`](../olmoearth_run_data/riparian_extent/deploy_extent_map.py)

## Why this exists

The FM-vs-RF deploy spec (`specs/2026-07-19-fm-vs-rf-deploy-decision.md`, PR #70) says the foundation
model must beat an **honest median-mosaic RF baseline** on cross-reach transfer, not a strawman. This is that
baseline — and running it properly turned a convenient number into a real, sharper finding.

## The path to the number (each step corrected the last)

1. **Single-scene RF, 2 reaches** → Farmington↔Malpais transfer **0.42–0.53**. Suspiciously bad.
2. **Median mosaics** (receipt #20 compositing) → barely better (0.42–0.74). Median mosaics did *not*
   rescue it — so it isn't the compositing.
3. **A diagnostic** (is it real domain shift or a sampling artifact?) settled it: **each reach is
   cleanly separable in-domain** (full-feature 3-fold CV: Farmington **0.925**, Malpais **0.899**), but
   the decision boundary **does not transfer** between them. Labels and negatives are sound; the
   spectral signature of "riparian" is genuinely reach-specific. **Real morphological domain shift, not
   an artifact.**
4. **Diverse-reach pooling** — the fix the diagnostic implied: train on *morphologically diverse*
   reaches, not just more of them.

## The result — 4 morphologically-diverse reaches, hold-one-out, median mosaics

| held-out reach | morphology | transfer AUC |
|---|---|---|
| Farmington | wide San Juan/Animas confluence | **0.905** |
| Aztec/Animas | narrower montane-fed tributary | **0.886** |
| Kirtland | semi-arid mainstem | **0.845** |
| **Malpais** | **narrow ephemeral arroyo** | **0.557** |

*Trained on ~1.7 M pooled labelled pixels across the other three reaches each time; deploy map over a
held-out Bloomfield reach = 8,511 polygons (down from 11,688 single-scene).*

## The finding

**Diverse-reach pooling closes the transfer gap for the *common* morphology and leaves exactly one
hole.** The three river-corridor reaches jump to **0.85–0.91 (mean 0.88)** once the pool spans river
types — a per-pixel RF, trained on morphologically diverse reaches, transfers *well* to unseen river
corridors. But **the arroyo stays at 0.557**, because it is the **only** arroyo: hold it out and nothing
in training represents an ephemeral, sparse, dryland corridor, so the river-trained boundary is
anti-correlated on it.

This is the most useful outcome the baseline could produce, because it says precisely **where RF is
enough and where it is not**:

- **Common morphology (river corridors):** pooled RF ≈ **0.88**. The FM will have to work hard to beat
  that — the GPU is likely *not* justified here.
- **Under-represented morphology (the arroyo):** RF fails at **0.557**. This is exactly the
  "hard/label-scarce transfer to unseen ground" the CPU pre-flight named as the FM's *one* predicted
  win (+0.04–0.08 ROC). **The arroyo is the honest test of whether OlmoEarth earns the GPU.**

## What it sharpens for the FM decision

The question is no longer the vague "FM vs RF." It is: **can OlmoEarth's spatial context generalise to
an under-represented morphology (the arroyo) that a per-pixel RF cannot — from few examples?** That is a
single, falsifiable experiment against a bar of 0.557, with a real prior that this is precisely the FM's
predicted strength. The other FM claim — spatially-coherent maps — also has its baseline here: even the
best pooled RF map is 8,511 fragments (salt-and-pepper), which the FM's 32×32 context is meant to fix.

The corollary vindicates the "train beyond one reach" instinct, with a twist: **it was never about the
*count* of reaches — it was about their *morphological diversity*.** A cheap data-collection lever
(cover each morphology) closes most of the gap for free; the residual (rare morphologies) is where a
foundation model, if anywhere, earns its keep.

## Reproduce

```
PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/deploy_extent_map.py \
    --gdb <path>/GRSJ_Version2_0Plus_North.gdb
```

Trains on the four diverse reaches, reports hold-one-out transfer, and writes a riparian-extent GeoTIFF
+ GeoJSON over the held-out Bloomfield reach. Per-reach median cubes are cached on the data drive, and
GDAL temp is pinned there too (see receipt #23 — the boot-disk-fill this run first taught us the hard
way).
