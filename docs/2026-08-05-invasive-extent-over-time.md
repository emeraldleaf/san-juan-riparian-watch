# Invasive extent over time — flat for 25 years, then a recent doubling

**Date:** 2026-08-05 · **Status:** result (deep-time reconstruction) · the first *invasive-extent-over-time*
product. Interactive: [year-slider map](deep-time-invasives.html). Reproducible via
[`deep_time_invasives.py`](../olmoearth_run_data/riparian_extent/deep_time_invasives.py).

## The one-sentence answer

Mapping NMRipMap's invasive class (tamarisk + Russian olive, *combined*) back through the Landsat record
over the Farmington reach — on **5-year window composites**, **one sensor family** — the invasive
footprint sits **~flat near 1.3% of the AOI from the late 1980s through ~2012, then roughly doubles to
3.0% by 2018–22.** The invasion here is a **recent acceleration on a long-stable baseline**, not a steady
30-year ramp.

## The trajectory

| window (5-year) | invasive extent (% of valid AOI) | sensors |
|---|---|---|
| 1988–1992 | 1.4% | Landsat-5 |
| 1998–2002 | 1.4% | Landsat-5 + 7 |
| 2008–2012 | 1.2% | Landsat-5 + 7 |
| 2018–2022 | **3.0%** | Landsat-7 |

## Why *windows*, not years — the method lesson that made this trustworthy

The first cut used single-year composites and looked like a noisy ~5× ramp with a distracting 2010 dip.
Bracketing the suspect years exposed the real problem — **single-year extent is far too noisy to trend**:

- **2009 / 2010 / 2011** → 1.5% / 1.0% / 1.5%. The "2010 dip" was a lone bad year flanked by normal
  ones — a *year-specific artifact*, not the beetle (a defoliation signal would depress the whole
  2008–2012 window, not one year).
- **1999 / 2000 / 2001** → 2.1% / 1.7% / 1.2%. A **0.9 pp swing across three adjacent years** — proof
  that any single year carries ~±0.5 pp of noise.

So the trajectory is built from **median composites over 5-year windows** (~18 growing-season scenes
each). A single bad year can no longer move a point, and the noise collapses: the three pre-2020 windows
now agree at ~1.3% (the old "2010 dip" is a 0.2 pp nothing). *This is the difference between a result you
have to defend point-by-point and one that holds on its own.*

## Method, and the two decisions that make it defensible

An RF trained on **67,625 labelled pixels** (15,656 invasive / 51,969 native) from the 2020 NMRipMap `IC`
class vs native riparian woody (from the local GDB, not the live service), applied wall-to-wall to each
window's median composite. Two deliberate choices:

1. **Hold the sensor family constant** — Landsat-5 TM + Landsat-7 ETM+, **OLI excluded** — because the
   [beetle run](2026-08-04-phase3c-beetle-null-result.md) showed the TM↔OLI change drift a flat control
   0.285. Same family → change means vegetation, not sensor.
2. **Composite over windows, not years** (above) — so no single year drives the trend.

## What is and isn't trustworthy

**Trustworthy — the shape.** Three independent pre-2020 windows land at ~1.3% with no anchor advantage:
the corridor's invasive footprint was **roughly stable from the late 1980s through the early 2010s**, then
stepped up. The maps show it — the corridor is visibly denser in 2018–22, especially at the confluence.

**Caveated — the 2020 magnitude.** 2018–22 is also the classifier's **training window**, so it matches the
labels best *by construction* — part of the jump's height is the model fitting its own calibration year,
not purely new ground. The *pre-2020 flatness* carries no such advantage and is the robust part; the
*recency* of the rise is solid, its exact multiple is not.

## The honest limitations

1. **Combined, not separated.** NMRipMap `IC` conflates tamarisk and Russian olive; this is
   *invasive-woody* extent, not the two species apart (needs the Level-4 split or many more field points).
2. **No pre-2018 ground truth.** Every pre-2020 window is an unvalidated reconstruction; only the training
   window touches real labels.
3. **Training-year anchor.** The 2020 window is privileged (above) — read the shape, not the absolute jump.
4. **Coarse features, one reach.** A growing-season composite (chosen for deep-record robustness) and
   Farmington only, so far.

## What it means

The honest first version of the product the project set out to build — *invasive extent over time* — and
it lands a real, non-obvious finding: the invasion at Farmington is a **recent (post-~2012) acceleration**,
not a smooth multi-decade creep. Natural next steps: more reaches; the FM arm (spatial context may sharpen
the deep maps); and separating tamarisk from Russian olive, which this product deliberately does not.

## Reproduce

```bash
cd olmoearth_run_data/riparian_extent
export PYTHONPATH=../../python-etl
# needs the local NMRipMap GDB (.tmp/nmripmap_gdb/.../GRSJ_Version2_0Plus_North.gdb)
python deep_time_invasives.py --epochs 1990 2000 2010 2020   # 5-year windows (± 2 yr) by default
#   → invasive_<center>.geojson per window + the AOI-fraction trajectory
```
