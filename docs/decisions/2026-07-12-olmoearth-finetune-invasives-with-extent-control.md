# ADR: Fine-tune OlmoEarth on invasives, with extent as a calibration control

**Date:** 2026-07-12 · **Status:** Accepted (planning) · **Supersedes:** nothing
**Tracks:** issue #9 · **Scaffold:** `olmoearth_run_data/riparian_extent/`

## Context

We are about to spend GPU time fine-tuning OlmoEarth. Two things constrain what that run
should target.

**Extent is already solved.** CO-RIP (Woodward et al. 2018) mapped riparian corridor +
vegetation for the entire Colorado Basin — including the San Juan — at median κ 0.80. Our own RF
baseline reaches **pixel-level spatial-CV F1 0.90–0.92** on the NMRipMap-trained NM tiles. A
successful extent fine-tune therefore buys a *benchmark*, not a contribution: "our foundation
model matches a 2018 paper, and also beats the RF we wrote ourselves."

**Invasives is the actual gap.** Nobody has produced a wall-to-wall, time-series,
native-vs-invasive cover product at reach scale — CSU call their occurrence points and the extent
maps *"complementary products rather than a single integrated map of invasive versus native
species."* And the discriminator for Tamarix is **late-season senescence phenology**, which is
exactly the signal a temporal foundation model exists to exploit and exactly what our frozen-Nano
harness was destroying. This is the task where the FM has a mechanistic reason to win and
RF-on-hand-features has a reason to struggle.

So the run should target invasives. The problem is what happens when it fails.

**A bad invasives number, run alone, is uninterpretable.** Suppose we get F1 0.15. At least four
explanations fit equally well:

1. our rslearn / `olmoearth_run` pipeline is misconfigured (normalization, label alignment, split);
2. fine-tuned OlmoEarth genuinely cannot do fine-grained species discrimination here;
3. **332** Tamarix/Russian-olive polygons (NMRipMap `L2 = IC`, Animas) is simply too few labels;
4. the **beetle confound** ate the signal — *Diorhabda* was released directly on the San Juan
   (2004–07), and defoliated Tamarix **browns early**, inverting the senescence discriminator.

Nothing in a single number separates those. This is precisely the trap the first OlmoEarth
attempt fell into: it reported "the foundation model is worse" when the causes were a broken
harness (mean-pooling over time) and corrupted labels (~45% wrong). See
`docs/olmoearth-vs-rf-baseline.md`. Repeating that mistake with a *more expensive* experiment is
the failure mode this ADR exists to prevent.

## Decision

**Run extent first, as a calibration control, in the same GPU session. Then retarget to invasives.**

### Step 1 — Extent (the control)

Fine-tune `OLMOEARTH_V1_BASE` per Ai2's `mangrove` recipe (`FreezeUnfreeze` @ epoch 20, 10× LR,
`SegmentationPoolingDecoder`, 12 monthly S2 mosaics) on the existing scaffold: classes
`1 = riparian, 2 = water, 3 = other`, NMRipMap labels, spatial split.

Extent is the right control because it is the one task where **we already know what good looks
like**, and it isolates the pipeline from every confound above:

- known-good reference number on the same AOI, labels and folds (RF);
- thousands of labels, not 332 — so label scarcity is off the table;
- **no beetle confound** — defoliation changes what a species *looks like*, not whether the
  vegetation is riparian;
- Ai2's own analogous recipe reports 97.6% OA, so a correctly-run fine-tune should be strong.

It answers exactly one narrow question: **does our fine-tuning pipeline work at all?**

> ### ⚠️ Compare against the PIXEL-level RF number, not the patch-level one
>
> There are two RF baselines in this repo and they are **not interchangeable**:
>
> | | Granularity | Scope | F1 |
> |---|---|---|---|
> | Stage-1 delineation | **pixel (10 m)** | full NM tiles, spatial-CV | **0.90–0.92** |
> | `olmoearth-fair-test` | patch (80 m) | 15%-riparian Malpais sub-AOI | 0.701 |
>
> `SegmentationPoolingDecoder` predicts at **pixel/segment** level, so its comparison target is
> **0.90–0.92**. Scoring a pixel-level fine-tune against the 0.701 patch number would flatter it
> by ~0.2 F1 and manufacture a win. The 0.701 number belongs to the *frozen-embedding + RF-head*
> experiment and stays there.

### Step 2 — Invasives (the contribution)

Same cube, same code path, same folds; swap the label layer to Tamarix / native / other using
NMRipMap `L2 = IC` (introduced woody riparian). This is a head swap and a retrain, not a new
pipeline.

### The decision table

| Extent (control) | Invasives | Reading |
|---|---|---|
| **fails** (≪ 0.90 pixel F1) | — | **Stop.** Our pipeline is broken; any invasives number is noise. Debug before spending more GPU. |
| **strong** (≳ 0.90) | strong | The contribution lands: a wall-to-wall native-vs-invasive map. |
| **strong** | weak | **A real finding, not a shrug.** The pipeline demonstrably works, so a weak result means the *task* is hard — and we can then attribute it (label scarcity vs. beetle confound) as a scientific question. |

That bottom-right cell is the entire justification for the control. Without it, a weak invasives
result is an embarrassing shrug. With it, it is a defensible negative result — and given the
beetle geography, a genuinely interesting one.

## Consequences

- **Cost is ~an hour of GPU, not a second project.** Same session, same cube, same code path —
  the control is a label-layer swap and a retrain. Per the hosting ADR, compute is on-demand
  batch (Modal / RunPod), so idle cost is $0.
- **It closes #9 as a side effect.** The extent control *is* the head-to-head #9 asks for (does
  fine-tuned Base beat the RF baseline on the same folds?). We get the answer to the open
  scientific question for free, on the way to the contribution.
- **We must resist reporting only the control.** A strong extent result is the tempting headline
  ("foundation model beats baseline!") and is also the least interesting thing we could say, since
  CO-RIP already did it. It is a gate, not a deliverable.
- Both results get published either way, per the project's standing rule. The retraction in
  `docs/olmoearth-vs-rf-baseline.md` is the precedent.

## Alternatives rejected

- **Invasives only.** Cheapest, and uninterpretable on failure — see Context. Rejected.
- **Extent only** (the scaffold as it stands, closing #9 as scoped). Answers the benchmark
  question cleanly but reproduces published work and never reaches the actual gap. Rejected as an
  endpoint; retained as Step 1.
- **Skip the fine-tune entirely.** Defensible — the fair-test retraction already tells an honest
  story. But it leaves the one genuinely open scientific question in the project unanswered, and
  the frozen-Nano + RF-head configuration we *did* test is one Ai2 endorses nowhere. Rejected.

## Known risks (record them now, not after the run)

- **332 invasive polygons is thin.** Overfit risk is real. Mitigating framing: "better accuracy
  from scarce labels" is the FM's central claim, so this is a fair test of that claim, not a
  rigged one.
- **The beetle confound has no clean control area.** *Diorhabda* reached virtually all Upper Basin
  rivers by 2014. If the senescence signal is unstable year to year, that is a finding — but it
  will be hard to distinguish from "the model failed." Expect to need multi-year runs to separate
  them.
- **NMRipMap conflates Tamarix with Russian olive** (both are `IC`). The CSU/NREL occurrence
  points can split them, but that is a later refinement, not Step 2.
