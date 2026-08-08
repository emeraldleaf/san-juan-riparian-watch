# The beetle didn't break the discriminator — and the control proves we couldn't have seen it if it had

**Date:** 2026-08-04 · **Status:** result (negative) · runs the CPU/RF arm of the
[Stage-2 invasives/beetle gate](specs/2026-08-01-stage2-invasives-beetle-gate.md) on the real CSU
field points. Reproducible via
[`phase3c_invasives_beetle.py`](../olmoearth_run_data/riparian_extent/phase3c_invasives_beetle.py).

## The one-sentence answer

The pre-registered prediction — that a present-day-trained tamarisk classifier would **invert**
(AUROC < 0.5) when pushed back before the tamarisk beetle — is **falsified**: tamarisk-vs-native holds
**0.81–0.86 across 2020 → 2015 → 2000** (0.849 / 0.813 / 0.862), never near a flip. And the pre-registered
**negative control (Russian olive) dropped 0.34** over the same span (0.891 → 0.553) — so even the faint
signal that *is* in the expected direction sits well inside the noise this data carries. **The
discriminator is beetle-robust, and this in-basin sample is too small and too cross-sensor-confounded to
resolve a subtle beetle effect anyway.**

---

## What the test was

The beetle-inversion hypothesis (see [the spec](specs/2026-08-01-stage2-invasives-beetle-gate.md)):
pre-beetle tamarisk greens early *and holds green late* — a longer season than cottonwood; the beetle
defoliates it mid-summer, so post-beetle tamarisk browns *early*. The discriminative phenology cue
**flips sign** across the beetle's arrival (~2004–07 on the San Juan). So a model trained on today's
imagery should, in theory, get pre-beetle tamarisk *backwards*.

**Test C1** scores the same known stands on 2020 (Landsat-8) vs 2000 (Landsat-5, pre-beetle) Landsat,
per taxon, with **Russian olive as a negative control** — it is not beetle-defoliated, so it should
**not** move. Ground truth: **167 CSU 2017 field points** fall in the San Juan basin; the **135** that
carry one of the three scored species labels are used here (47 tamarisk, 49 Russian olive, 39 native) —
the remaining 32 are other/non-riparian classes this gate drops. Leave-one-**spatial-block**-out CV
(~2 km tiles, `n_splits` = block count) — the in-basin points are effectively one field cluster
(SW Colorado), so leave-one-*trip*-out is impossible (a trip can be single-class).

## The result

| taxon-vs-native | 2020 (Test A) | 2015 post-beetle | 2000 **pre-beetle** | Δ(2000−2020) |
|---|---|---|---|---|
| **tamarisk** (signal) | 0.849 | 0.813 | **0.862** | **+0.013** |
| **Russian olive** (control) | 0.891 | 0.767 | **0.553** | **−0.338** |

Two readings, and the second is the important one:

1. **No inversion.** A 2020-trained model still ranks tamarisk-vs-native at **0.862 in 2000** — nowhere
   near the predicted < 0.5. There is a *faint* move in the predicted direction (post-beetle 0.813 <
   pre-beetle 0.862, consistent with the beetle removing the late-season cue), but it is ~0.05.
2. **The control vetoes it.** Russian olive — which the beetle does not touch — **cratered 0.338**
   pre-beetle. A control that should be flat instead moved ~7× more than the tamarisk "signal." So the
   cross-era comparison is **dominated by non-beetle drift** — the Landsat-5↔8 sensor change (3A measured
   the S2→Landsat penalty at +0.046, but TM↔OLI at 30 m over a ~40-point class is noisier) plus small-
   sample variance. That ~0.34 noise floor dwarfs the ~0.05 tamarisk effect.

**This is exactly what pre-registering a control is for.** Declared in advance, Russian olive can *veto*
the result instead of being quietly dropped; without it, one could have over-read the 0.05 tamarisk
wiggle as "a hint of the beetle." With it, the honest statement is: **this data cannot demonstrate a
beetle inversion, and the discriminator looks more beetle-robust than the hypothesis assumed.**

## Why the discriminator might be beetle-robust

The hypothesis assumed the tamarisk↔native signal *is* the late-season senescence contrast. But an RF on
a 12-month median cube has other, beetle-invariant cues: **spring green-up timing**, canopy/spectral
differences, SWIR moisture. If those carry most of the separation, defoliation dents but does not flip
it — which is what 0.862 → 0.813 (a dip, not a flip) looks like.

## Where a reviewer *should* attack this — the honest limitations

1. **Underpowered.** One SW-Colorado field cluster, ~40 points per class, leave-one-2-km-block-out CV.
   Spatial blocks *within* one cluster are a weak transfer test; the AUROCs are usable but coarse.
2. **The sensor confound is real and unquantified here.** 2000 = Landsat-5 TM, 2020 = Landsat-8 OLI; the
   control's −0.338 is the clearest evidence that TM↔OLI + small-n drift, not the beetle, drives the
   cross-era deltas. The result is *net of* that only qualitatively.
3. **Persistence assumption.** We assume a 2020 tamarisk stand was tamarisk in 2000 (tamarisk is
   long-lived), and beetle-killed stands bias 2020 `IC` toward *under*-counting 2000 tamarisk.
4. **30 m Landsat** blurs narrow stands — worse for species than for extent.

## What it means for Stage 2

The RF-on-CSU arm returns a **clean null with a clear cause**: the in-basin field data can neither confirm
nor exclude the beetle inversion, because its own negative control shows the cross-era noise is too large.
Settling the beetle question therefore needs **(a)** the FM arm (spatial context may carry a
beetle-invariant signal the per-pixel RF can't), and/or **(b)** more and better-sampled species labels
across the basin and the sensor eras — not more RF runs on this data. The [C2 defoliation-signature
test](specs/2026-08-01-stage2-invasives-beetle-gate.md) (present-day, real `is_beetle_affected` labels on
the Plateau pool) sidesteps the sensor confound entirely and is the better next RF experiment.

## Reproduce

```bash
cd olmoearth_run_data/riparian_extent
export PYTHONPATH=../../python-etl
# needs TabletData_2017.csv (CSU, CC BY-SA, ~326 KB from mountainscholar)
python phase3c_invasives_beetle.py --csv TabletData_2017.csv
#   → tamarisk-vs-native and Russian-olive-vs-native AUROC for 2020 / 2015 / 2000
```
