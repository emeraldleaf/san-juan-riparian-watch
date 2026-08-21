# Stage 2 — native-vs-invasive, and does it survive the beetle

> **⚠ Retracted / under review (2026-08-21):** the “desert arroyo rescue” (RF 0.557 → OlmoEarth 0.889) is retracted pending a scoring audit — “Malpais” is the **river-dominated subwatershed** HUC12 “Malpais Arroyo–San Juan”; the models map the river while the truth follows the wash, and the **arroyo may never have been modeled**. See [RETRACTIONS.md](RETRACTIONS.md) → `arroyo-rescue-attribution-2026-08-21`.

**Date:** 2026-08-01 · **Status:** experiment spec (spec-before-spend) · the Stage-2 analogue of the
settled [Stage-1 extent LORO result](../2026-08-01-fm-vs-rf-loro-result.md) · depends on
[Phase 3 deep-time](2026-07-18-phase3-deeptime-change.md),
[beetle training pool decision](../decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md) ·
labels via [`csu_points.py`](../../python-etl/riparian/labels/csu_points.py) + NMRipMap `IC`.

## The question, honestly framed

Stage 1 settled *where* riparian vegetation is (extent). It was decided on extent **alone** — invasives
were explicitly out of scope. This spec defines the next gate: separating **native (cottonwood/willow)
from invasive (tamarisk, Russian olive)**, and — the part that is the project's actual novelty claim —
whether that separation **survives being pushed back through the Landsat record across the tamarisk
beetle's arrival**. Extent is a solved problem in the literature (CO-RIP did basin-wide extent). *An
annual, beetle-aware, native-vs-invasive product over the deep record does not exist.* One experiment
can either open it or show why it is hard. Like the extent gate, it is pre-registered and decided by a
number.

## Why the beetle is the whole ballgame

The tamarisk leaf beetle (*Diorhabda*) was released on the San Juan ~2004–2007. It defoliates tamarisk
**early**, and that **inverts the discriminative phenology cue**:

- **Pre-beetle** tamarisk greens early *and holds green late* → a **longer** season than native cottonwood.
- **Post-beetle** tamarisk is defoliated mid-summer → browns **early** → a **shorter** effective season
  than native.

The sign of the tamarisk-vs-native cue **flips across the beetle transition.** A model trained on
present-day (post-beetle) imagery learns "tamarisk browns before native"; applied to pre-beetle imagery
it should see tamarisk-stays-green-*longer* and call it native. This is not a weakened signal — it is a
**reversed** one, and it is the exact confound the project flags: *a greenness decline in a tamarisk
reach is biocontrol working, not the corridor recovering.* This gate turns that confound into a measured
number.

## The labels (already in place)

- **Species truth — training:** NMRipMap v2.0 Plus `IC` code = free tamarisk/Russian-olive polygons
  (2020, NM), via the `L2_Code` filter in `riparian/labels/nmripmap.py`; native riparian-woody polygons
  as the negative. Polygons, not points — enough to *train* (unlike Stage-1's 167-point problem).
- **Species truth — validation:** the **CSU 2017 field points** through
  [`csu_points.py`](../../python-etl/riparian/labels/csu_points.py) — ~148 inside the San Juan basin
  (45 Russian olive, 37 tamarisk, plus native), species-level and independent.
- **The beetle state — real labels:** `csu_points` models tamarisk condition as a **first-class state**
  (`is_beetle_affected`: defoliated / live-dead-mix / dead — **547 beetle-affected records** across the
  Colorado Plateau, though **0 inside the San Juan basin** — hence *train the beetle signature on the
  ecoregion-matched Plateau pool and transfer*, per the [pool decision](../decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md)).
- **Sensor:** Landsat (30 m) — the only sensor reaching pre-beetle (1984→). Point-sampled, the
  [3B harness](../../experiments/riparian_extent/phase3b_temporal.py). Landsat-5 TM for 2000,
  Landsat-8 OLI for 2015/2020; the `landsat-c2-l2` collection serves common-name bands across sensors.

## The three nested tests

### Test A — is the species signal there? (the gate)

RF **and** FM on invasive-vs-native, 2020 phenology cube, **spatial CV** (`assign_spatial_folds`, no
spatial leakage). Report **invasive-vs-native AUROC**. The analogue of the in-domain CV 0.90+ that
preceded Stage-1 LORO: if native and invasive are not separable *in-domain in 2020*, nothing downstream
matters. Tamarisk-vs-native and Russian-olive-vs-native likely need separate heads (different phenology).

### Test B — species transfer across reaches (the LORO analogue)

Leave-one-reach-out for the **species** task, FM vs RF, the same unbiased three-way split as Stage 1.
Does the FM's spatial context help species-ID transfer the way it rescued extent on the arroyo?

### Test C — the beetle axis, isolated (the real experiment)

The 3B trick — *score the same stands across a transition; interpret the change against the axes it
carries.* Two complementary sub-tests:

- **C1 — deep-time inversion (persistence-based).** Train **tamarisk-vs-native** on **2020** phenology;
  score the same stands on **2000** (pre-beetle) Landsat. Report AUROC(2020), AUROC(2000), and the drop.
  - **⚠ The sensor confound (do not skip).** 2000 is **Landsat-5 (TM)** and 2020 is **Landsat-8 (OLI)**:
    the 2020→2000 gap carries **sensor + beetle**, *not* the beetle in isolation — the "one axis" framing
    is false here. The control is [3A](../2026-07-18-phase3a-cross-sensor-result.md): the whole S2→Landsat
    sensor penalty was **+0.046 AUC**, nowhere near a sign flip, so a measured *inversion* (< 0.5) cannot
    be a sensor artifact. The magnitude of any non-inverting drop, though, must be read net of that ~0.05
    sensor allowance, and the beetle conclusion is **conditional on this control holding**.
  - **Taxon-split, not pooled.** Run C1 **per taxon** — tamarisk-vs-native *and* Russian-olive-vs-native —
    never a pooled "invasive-vs-native." Russian olive is **not** beetle-defoliated, so it is the built-in
    **negative control**: tamarisk should invert while RO should **not**. Pooling them would let the
    control mask the signal.
- **C2 — defoliation signature (real labels).** On the Plateau pool, train live-tamarisk vs
  beetle-affected-tamarisk (`is_beetle_affected`) from phenology; does the detector exist, and does it
  transfer to the San Juan?

## Pre-registered predictions + GO/ABORT

Pre-registered so the result cannot be rationalized after the fact:

1. **Test A (gate):** invasive-vs-native AUROC **≥ 0.75** in-domain (2020). Below that → the phenology
   signal is too weak; **ABORT** to richer features (SAR, texture, red-edge) before any deep-time claim.
2. **Test C1 (the headline prediction):** a 2020-trained RF **inverts** pre-beetle —
   **AUROC(2000) < 0.5**, and materially below AUROC(2020). This *confirming* is the publishable result:
   naive deep-time invasive mapping is actively wrong across the beetle transition.
3. **Test C — the FM's opening (the arroyo story again):** the FM holds **AUROC(2000) > 0.5** where the
   RF inverts, by learning era-invariant structure (stand shape, spatial arrangement) rather than the
   flipped phenology cue. If it does, Stage 2 **GO for the FM** on the same logic Stage 1 was decided —
   the FM rescues the regime the baseline is blind to. If the FM *also* inverts, deep-time invasives
   needs **era-aware modelling** (era-specific heads or a beetle covariate), not just a better backbone —
   and we will have said so with a number.

## The honest traps (bake in from the start)

- **Persistence + survivorship (C1):** we assume a 2020 tamarisk stand was tamarisk in 2000. Mostly true
  (tamarisk is long-lived, does not revert) — *but* beetle-killed stands mean 2020 `IC` **under-counts**
  2000 tamarisk, biasing toward missing dead stands, not toward a false inversion. State it in the result.
- **No pre-beetle ground truth exists.** The beetle penalty is measured as degradation/inversion of a
  post-beetle classifier at persistent stands — never from pre-beetle labels (there are none).
- **Landsat 30 m** loses narrow stands; a mixed 30 m pixel is worse for species than for extent.
- **Russian olive ≠ tamarisk** — RO is not beetle-defoliated, so it must be handled separately *and*
  serves as the C2 control (its signal should not invert).
- **Two AUCs are not pixel-identical** — same nuance as Stage 1; the arroyo-scale effects dwarf it, small
  deltas do not.

## The cheap first move — no GPU

**Test A + C1's RF arm is CPU-only** (point-sampling + RF, the 3B harness). Scaffolded at
[`phase3c_invasives_beetle.py`](../../experiments/riparian_extent/phase3c_invasives_beetle.py),
ready to run the moment the Landsat 2000/2015/2020 pulls land. If it shows the inversion, **the single
plot — invasive-vs-native AUROC crossing below 0.5 as you walk back through the beetle era — is a
publishable result on its own**, and it justifies the FM/GPU arm. Highest information-per-dollar move in
the Stage-2 program; it does not depend on a rented GPU.

## Reproduce

```bash
cd experiments/riparian_extent
export PYTHONPATH=../../python-etl
# CPU arm — Test A (separability) + Test C1 (beetle deep-time inversion) on the CSU points
python phase3c_invasives_beetle.py --csv TabletData_2017.csv --years 2020 2015 2000
#   → reads invasive-vs-native AUROC per year; the 2020→2000 drop (and sign) is the beetle penalty
```

The FM arm (Tests B + the C GO/ABORT) is the Stage-1 LORO machinery pointed at the species labels, on a
rented CUDA box — spec'd here, run when Test A/C1 justify the spend.
