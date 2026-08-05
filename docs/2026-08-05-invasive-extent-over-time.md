# Invasive extent over time — the footprint expanded ~5× (and the 2010 dip we won't over-read)

**Date:** 2026-08-05 · **Status:** result (deep-time reconstruction) · the first *invasive-extent-over-time*
product. Interactive: [year-slider map](deep-time-invasives.html). Reproducible via
[`deep_time_invasives.py`](../olmoearth_run_data/riparian_extent/deep_time_invasives.py).

## The one-sentence answer

Mapping NMRipMap's invasive class (tamarisk + Russian olive, *combined*) back through the Landsat record
over the Farmington reach — on **one sensor family** so change means vegetation, not sensor — the invasive
footprint **expands ~5×, from 0.7% of the AOI in 1990 to 3.3% in 2020**. The multi-decade invasion is
plainly visible; a **non-monotonic 2010 dip** is real in the numbers but **not cleanly attributable** —
the trend is the finding, not any single year.

## The trajectory

| year | sensor | invasive extent (% of valid AOI) |
|---|---|---|
| 1990 | Landsat-5 TM | 0.7% |
| 2000 | Landsat-5 + 7 | 2.1% |
| **2010** | Landsat-7 (SLC-off) | **1.0%** ← dip |
| 2020 | Landsat-7 ETM+ | 3.3% |

## Method, and the one decision that makes it defensible

An RF trained on **67,625 labelled pixels** (15,656 invasive / 51,969 native) from the 2020 NMRipMap
`IC` class vs native riparian woody, on a growing-season median Landsat composite, then applied
wall-to-wall to each epoch. The decision that separates a trajectory from an artifact: **hold the sensor
family constant.** The whole series is **Landsat-5 TM + Landsat-7 ETM+ — Landsat-8 OLI is deliberately
excluded** — because OLI's different band response was exactly what made the flat control drift 0.285 in
the [beetle run](2026-08-04-phase3c-beetle-null-result.md). Same sensor family, same classifier, same
compositing → the year-to-year *change* is far more trustworthy than any epoch's absolute number.

## What is and isn't trustworthy here

**Trustworthy — the direction.** 1990 is the lowest and 2020 the highest by a wide margin; the ~5×
expansion tracks the known tamarisk/Russian-olive invasion of the San Juan over these decades. The 2020
value is anchored to the labels by construction; the deep maps are held to the *same* method, so the
*slope* is the signal.

**Not trustworthy — any single year, especially 2010.** The 2010 point (1.0%, below 2000's 2.1%) has two
readings we cannot separate with this data:

1. **The tamarisk beetle.** 2010 sits in the beetle's peak-defoliation window (released 2004–07);
   defoliated tamarisk reads *less* like the 2020-trained "healthy invasive" class, so detected extent
   would genuinely drop. That would be a real ecological signal — biocontrol knocking back detectable
   cover — and it rhymes with the whole Stage-2 beetle thesis.
2. **Sensor / noise.** 2010 is **Landsat-7-only** (SLC-off diagonal gaps), a single-season 6-band
   composite. The wobble could simply be that.

Honestly: **we can't tell which.** Naming both and claiming neither is the correct call — the same
discipline the beetle result used with its control.

## The honest limitations

1. **Combined, not separated.** NMRipMap `IC` conflates tamarisk and Russian olive; this is *invasive-woody*
   extent, not the two species apart (that needs the Level-4 split or many more field points).
2. **No pre-2018 ground truth.** Every deep epoch is an unvalidated reconstruction; only the 2020 anchor
   touches real labels.
3. **Coarser features than the phenology cube.** A single growing-season 6-band composite (chosen for
   deep-record robustness) separates less sharply than the 12-month cube — this is an *extent* map, not a
   fine-grained cover estimate.
4. **One reach.** Farmington only, so far.

## What it means

This is the honest first version of the product the project set out to build — *invasive extent over time*.
It works, the trend is credible, and it's transparent about its own error bars. Natural next steps: extend
to more reaches; add the FM arm (spatial context may sharpen the deep maps); and — the interesting one —
test whether the 2010 dip survives on a beetle-independent sensor path, which would start to separate
"biocontrol" from "SLC-off noise."

## Reproduce

```bash
cd olmoearth_run_data/riparian_extent
export PYTHONPATH=../../python-etl
# needs the local NMRipMap GDB (.tmp/nmripmap_gdb/.../GRSJ_Version2_0Plus_North.gdb)
python deep_time_invasives.py --epochs 1990 2000 2010 2020
#   → invasive_<year>.geojson per epoch + the AOI-fraction trajectory
```
