# Invasive extent over time — a robustness cautionary tale, and the reliable product it pointed to

**Date:** 2026-08-05 · **Status:** result (a *negative* on the deep-time trajectory, a *positive* on the
present-day map) · reproducible via
[`deep_time_invasives.py`](../olmoearth_run_data/riparian_extent/deep_time_invasives.py).
**Reliable product:** [the present-day corridor-vs-invasive map](extent-vs-invasive.html).

## The one-sentence answer

Trying to map invasive extent *back through the Landsat record* is **not robust before ~2000** — the
historical numbers swing ~1 pp with the compositing recipe no matter what normalization you apply, so no
trajectory shape can be claimed. What the effort *did* deliver, honestly, is the reliable **present-day**
product: **23% of Farmington's riparian corridor is invasive** — a figure the model reproduces from the
NMRipMap labels it was trained on (in-sample calibration, not an independent validation).

## The reliable result: the corridor vs the invaders within it

The [interactive map](extent-vs-invasive.html) (present-day, 2020, label-anchored): the predicted
riparian-woody **corridor** (7.6 km²) with the **invasive share within it** (1.7 km²) highlighted.

> **23% of the mapped corridor is invasive tamarisk / Russian olive** — and the masked prediction
> *reproduces* the label proportion (15,656 / 67,625 woody-labelled pixels are invasive = 23%). Because
> the model was trained on those 2020 labels, this is an **in-sample calibration check, not an independent
> validation** — a spatially-held-out test is the proper next step.

This is the answer to "riparian extent vs invasive": not just *where* the green corridor is, but *how much
of it is the wrong plant*. It is a present-day map anchored to real labels — no reconstruction, no error
bar wide enough to swallow the signal.

## The cautionary tale: why the *over-time* trajectory can't be claimed

The first draft looked like a clean **~5× growth** with a distracting "2010 dip." Every check made it
worse, and the checks are the point:

1. **Single years are too noisy.** Bracketing exposed ~±0.5 pp of year-to-year noise — 1999/2000/2001 ran
   **2.1 / 1.7 / 1.2%**, and the "2010 dip" (2009/2010/2011 = 1.5/1.0/1.5) was a lone bad year, not the beetle.
2. **5-year windows didn't fix it.** A reasonable tweak — balancing scenes per year vs pooling the
   cleanest — moved 1990 from **1.4% to 2.5%** and flipped the shape. A robust result wouldn't care.
3. **Spectral indices didn't fix it.** Ratio features (NDVI, NDMI, MNDWI, NBR…) cancel *gain* drift, but
   1990 still swung **4.1% vs 5.5%** across window widths.
4. **Relative radiometric normalization got close, but not all the way.** Aligning each composite's
   per-band levels to the 2020 reference **stabilised 2000–2010** (2000 became identical across recipes)
   — but **1990 still swung 2.0% vs 3.0%.**

**The diagnosis is consistent:** 1990 is pure **Landsat-5 TM**, 30 years before the ETM+-anchored training
year, and it is too spectrally distant to reconcile. The middle of the record (roughly 2000–2015, where
the L5+L7 mix overlaps the training sensor) reconstructs reasonably; the pure-TM deep past does not. And
even the stabilised part barely moves — **2000 → 2020 is only ~0.8% → 1.4%** of area (the invasive layer is
now gated to woody vegetation, which removed non-vegetation false positives — a metal water tank was being
called tamarisk — and roughly halved the earlier estimate), a rise *at the level of the ±0.6 pp method-noise
on the anchor itself*. The dramatic "5×" was an artifact of an under-sampled 1990.

**So: no trajectory claim.** Continuing to tune the recipe past here would be fishing for a prettier line
— the cherry-picking failure the [method](method.md) exists to prevent.

## Why the present-day map *is* trustworthy when the trajectory isn't

The 2020 map is trained on 2020 imagery *and* calibrated to 2020 labels — it is *in-distribution*, so its
class proportions are anchored (the 23% match is that in-sample calibration). The historical maps are the
same model applied to out-of-distribution old imagery with **no ground truth to anchor them**. That
asymmetry is the whole story: present-day is anchored, deep-time is extrapolation. (An independent spatial
holdout would upgrade the present-day map from *calibrated* to *validated* — the honest next step.)

## The honest limitations (of the reliable product)

1. **Combined, not separated.** NMRipMap `IC` conflates tamarisk and Russian olive; this is
   *invasive-woody* share, not the two species apart.
2. **One reach, one year.** Farmington, 2020. Extending to more reaches is the obvious next step.
3. **Two independent classifiers.** The invasive layer is masked to the extent prediction (they are
   trained separately); the 23% is that masked intersection, which is why it matches the labels.

## What it means

The deliverable is the **present-day corridor-vs-invasive map** — reliable, label-calibrated, and exactly
the question a watershed manager asks. The deep-time trajectory is a documented *negative*: with a
present-day-trained RF on Landsat, invasive extent is **not reconstructable before ~2000**, and the change
since is too small to claim over the method noise. Getting *there* would need era-specific labels or a
sensor that resolves the phenology (which the incumbent literature also flags as the wall).

## Reproduce

```bash
cd olmoearth_run_data/riparian_extent
export PYTHONPATH=../../python-etl
# present-day corridor + invasive predictions → .tmp/present/{extent,invasive}_2020.geojson
python deep_time_invasives.py --target extent   --epochs 2020 --out .tmp/present
python deep_time_invasives.py --target invasive --epochs 2020 --out .tmp/present
# mask invasive to the corridor → the map's two layers + the 23% (post-processing step):
python - <<'PY'
import geopandas as gpd
ext = gpd.read_file(".tmp/present/extent_2020.geojson").to_crs(32612)
inv = gpd.read_file(".tmp/present/invasive_2020.geojson").to_crs(32612)
inv_in = inv.union_all().intersection(ext.union_all())
print(f"invasive-in-corridor: {100 * inv_in.area / ext.union_all().area:.0f}% of corridor")
gpd.GeoDataFrame(geometry=[inv_in], crs=32612).explode(index_parts=False).to_crs(4326).to_file(
    "../../docs/maps/present-invasive-in-corridor.geojson", driver="GeoJSON")
ext.to_crs(4326).to_file("../../docs/maps/present-extent-2020.geojson", driver="GeoJSON")
PY
#   deep-time (exploratory, NOT robust before ~2000):
python deep_time_invasives.py --target invasive --epochs 2000 2010 2020
```
