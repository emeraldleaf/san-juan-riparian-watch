# ADR: Fine-tune OlmoEarth on invasives, with extent as a calibration control

**Date:** 2026-07-12 · **Status:** Accepted (planning) · **Supersedes:** nothing
**Tracks:** issue #9 · **Scaffold:** `olmoearth_run_data/riparian_extent/`

> **Revised 2026-07-12 (same day), after review.** The first draft of this ADR framed extent as
> "already solved, therefore not a contribution" and treated the control as a throwaway benchmark.
> That was wrong in two ways, and it also missed a live defect in the fair test. Both corrections
> are folded in below; the two-step structure survives, with a much better justification.
> §"The real axis is TIME" and §"Label vintage" are the new material.

## Context

We are about to spend GPU time fine-tuning OlmoEarth. Three things constrain what that run
should target.

### The real axis is TIME — for extent *and* invasives

**Every existing product is a single frozen epoch.** CO-RIP (Woodward et al. 2018) is one static
raster. NMRipMap v2.0 Plus is one static map, photo-interpreted from **NAIP 2020**. Neither is a
time series. **Nobody has an annual riparian product for this basin — of extent OR of species.**

So "extent is solved" is too blunt. *Extent for one epoch* is solved. An **annual extent
trajectory over the EO record is not**, and neither is annual native-vs-invasive cover. The
contribution is the **time axis**, applied to both:

1. Match CO-RIP / NMRipMap for **one epoch** → this is *calibration*: it proves the model is
   trustworthy against an authoritative reference.
2. Roll the same model across the **EO record** → annual extent trajectories **and** annual
   invasive cover + spread.

This reframes the extent control. It is not a throwaway benchmark; **it is the calibration that
unlocks the time series.** A model you cannot trust for one epoch cannot be trusted for forty.

**And the archive is deep.** OlmoEarth natively supports `LANDSAT` and `NAIP` modalities, not just
`SENTINEL2` (verified: `Modality` enum in `olmoearth_pretrain_minimal`). For this AOI:

| Sensor | Record starts | Annual maps | Note |
|---|---|---|---|
| Sentinel-2 | **2015-10** | ~10 | 10 m; what our pipeline uses today |
| **Landsat** | **1984-04** | **~40** | 30 m; *and it is the sensor CO-RIP itself used* |
| NAIP | — | — | 1 m; **the imagery NMRipMap was interpreted from** |

> #### The beetle confound has no un-confounded PLACE — but it does have an un-confounded TIME
>
> We had written the *Diorhabda* confound off as unsolvable: the beetle reached virtually every
> Upper Basin river by 2014, so there is no clean control *area* in the AOI. True — but the
> beetle was only released in **2004–07**, and **Landsat reaches back to 1984**. That is a
> **~20-year pre-beetle era** in which the late-season-senescence discriminator holds
> uncontaminated.
>
> So the time axis does not merely *suffer* the confound — it is the only thing that can
> **isolate** it: characterise Tamarix phenology pre-2004, then measure what defoliation does to
> it afterward. This is a real experimental design and it exists only because of the temporal
> record.
>
> Caveats, stated now: Landsat is 30 m against narrow corridors, and our NMRipMap labels are from
> **2020 — post-beetle** — so applying them backwards is a domain shift, not a free lunch.

### Invasives is the species gap

Nobody has produced a wall-to-wall, time-series,
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

### Label vintage — train on imagery CONTEMPORANEOUS with the labels

**This is a live defect, not a hypothetical.** NMRipMap's own service metadata says:

> **NMRipMap Version 2.0 Plus** (Muldavin et al., **2023**) — *"a comprehensive review … leveraged
> high-quality 1-meter resolution ortho-photography from **2020** (NAIP 2020)"*

The labels were **photo-interpreted from 2020 imagery.** The fair test in
`docs/olmoearth-vs-rf-baseline.md` was run on **Sentinel-2 from 2024** — a **4-year label/imagery
gap**. We trained and scored 2020-vintage labels against 2024 reflectance, across which corridors
genuinely move: beetle defoliation, floods, channel migration, restoration plantings.

Consequences, stated precisely:

- The **relative** RF-vs-OlmoEarth comparison **still stands** — both arms ate the same mismatch.
- The **absolute** numbers are **pessimistic** for every arm. RF's 0.701 and OlmoEarth's 0.065 are
  both depressed by label noise we introduced ourselves.
- **For invasives it is much worse than for extent.** Riparian *extent* is fairly stable over four
  years; *Tamarix cover* is not — it is exactly what the beetle has been changing since 2004. A
  4-year gap is far more damaging to the species task than to the extent task.

**Decision: train on Sentinel-2 from the 2020 growing season**, contemporaneous with NAIP 2020.
S2 has covered the basin since 2015-10, so 2020 is fully available. Any epoch we *predict* may of
course be any year — but the epoch we *fit and validate against NMRipMap* must be 2020.

Generalised as a standing rule: **the training imagery year must match the label vintage.** If we
later adopt CO-RIP as a label source, its imagery is Landsat of *its* epoch, not 2020 S2 — and the
same rule applies.

## Decision

**Run extent first, as a calibration control, in the same GPU session. Then retarget to invasives.**
**Both fit on 2020 imagery, matching the label vintage.**

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

### Step 2 — Invasives (the species head)

Same 2020 cube, same code path, same folds; swap the label layer to Tamarix / native / other using
NMRipMap `L2 = IC` (introduced woody riparian). This is a head swap and a retrain, not a new
pipeline.

### Step 3 — Inference across the record (THE CONTRIBUTION)

Steps 1 and 2 produce a *calibrated model*. Step 3 is what nobody has done: **run it over every
year of the archive** and publish the trajectories.

- **Extent over time** — an annual riparian-extent series. CO-RIP is one epoch; this is the
  movie, not the frame. Novel on its own.
- **Invasives over time** — annual native-vs-invasive cover, and therefore *spread and retreat*.
  This is the product CSU explicitly say does not exist.
- **The beetle window** — if Landsat is used, the series spans **pre-2004 (beetle-free)** through
  the release years and after. That is the only way to separate "Tamarix senesces late" from
  "defoliated Tamarix browns early", and it turns the confound from a threat into the subject.

Sensor choice is a genuine open design question, not settled here:

| | Reach | Resolution | Trade-off |
|---|---|---|---|
| Sentinel-2 only | 2016–now (~10 yr) | 10 m | Resolves narrow corridors; **misses the entire pre-beetle era** |
| Landsat (or S2+Landsat) | 1984–now (~40 yr) | 30 m | Spans pre-beetle; **30 m may be too coarse** for the corridor |

Decide it after Step 1, on evidence: if the 10 m control barely resolves the corridor, 30 m Landsat
will not, and the pre-beetle ambition has to be scoped down or fused (S2 for resolution, Landsat
for reach). Do not commit to Landsat before we know the model works at 10 m.

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
