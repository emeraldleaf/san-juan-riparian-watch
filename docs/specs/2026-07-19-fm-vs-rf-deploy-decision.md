# FM-vs-RF, decided on the deployable map — where OlmoEarth 1.1 must earn its keep

**Date:** 2026-07-19 · **Status:** experiment spec (spec-before-spend) · depends on
[Phase 3 deep-time](2026-07-18-phase3-deeptime-change.md),
[GPU fine-tune plan](2026-07-12-gpu-finetune-execution-plan.md) · results feed
[methods & metrics](../2026-07-18-methods-and-metrics.md)

## The question, honestly framed

Every head-to-head so far says **RF ties the fine-tuned foundation model** on *aligned median-mosaic*
data: extent F1 within the label-noise band, invasives transfer AUC 0.80 = 0.80 ([methods §6](../2026-07-18-methods-and-metrics.md)),
sensor +0.046 and time +0.003 both model-agnostic ([3A](../2026-07-18-phase3a-cross-sensor-result.md),
[3B](../2026-07-18-phase3b-temporal-result.md)). So the burden of proof is **on the FM**. This spec
defines the one setting where it has a *structural* reason to win — the **deployable map** — and the
measured bar it must clear to justify the GPU and the OlmoEarth **1.1** upgrade. If it does not clear
the bar, **RF ships**, and we will have said so with a number.

## Why the deployable map is the right arena

Two FM properties are irrelevant in-domain but bite exactly where a deployed product lives:

1. **Spatial context.** RF is **per-pixel and context-free** — it classifies a 10 m pixel from its own
   72 numbers, blind to its neighbours, so its extent maps are **salt-and-pepper** and need
   morphological cleanup. OlmoEarth reads a **32×32 window with self-attention**; it can learn "riparian
   *because* it sits in a corridor-shaped patch along a drainage." For a **map a watershed manager will
   look at**, coherence is the product, not a nicety.
2. **Transfer to unseen ground.** Deployment = predicting reaches you did **not** train on. The binding
   constraint surfaced by 3B and confirmed here: a per-pixel RF on **single-scene** features collapsed
   cross-reach to **AUC 0.527** (Farmington→Malpais) — the exact [receipt #20](../method.md) failure.
   The CPU pre-flight predicted the FM wins *only* on "hard/label-scarce transfer to unseen ground
   (+0.04–0.08 ROC)." Cross-reach transfer **is** that setting.

## The baseline must be honest — median mosaics, not single-scene

**The current single-scene RF (0.527) is not the baseline.** It is the receipt-#20 artifact and would
rig the comparison in the FM's favour. The RF baseline for this decision is **median-mosaic RF** —
the same 12-month aligned compositing `materialize_reach.py` produces, which took Farmington→Malpais
from 0.37 to 0.80. **Step 0 — rebuild the RF baseline on median mosaics — is done** (PR #71: LORO
macro-mean AUC **0.798**, the bar tabulated below). The FM must beat *that*, not the strawman.

## The one task this gate controls

**Extent, and only extent.** The gate is the **`silver.riparian_extent` binary pixel task** — riparian
woody vegetation vs not, the deployment-target product. It is decided on that task **alone**: invasives
(Stage 2, native-vs-invasive) is **out of scope for this decision** and does not enter GO/NO-GO. The
deployable map is an extent product; the FM earns the GPU on extent or it does not earn it here.

- **Positive labels:** NMRipMap v2.0 Plus riparian-woody polygons, via the `L2_Code` filter in
  `riparian/labels/nmripmap.py` — never raw NMRipMap. **Negatives:** pixels sampled outside the positive
  polygons within each reach bbox (the same sampling `baseline.py` uses).
- **Footing (identical for both models):** 12-month aligned median-mosaic cubes from
  `materialize_reach.py` — *not* `deploy_extent_map.py`'s single-scene fetch. Same cubes, same pixels,
  same spatial folds feed RF and FM.
- **Aggregation:** **leave-one-reach-out (LORO)** across the **4 diverse reaches** (Farmington · Aztec/
  Animas · Kirtland · Malpais). Report **per-reach held-out AUC** and the **unweighted macro-mean** across
  the 4 folds. The macro-mean weights the arroyo equally with the three river corridors on purpose — it is
  the one under-represented morphology and the pre-flight's predicted FM-win setting.

## The bar is measured, not hypothetical — median-mosaic RF, LORO

Step 0 is **done** (PR #71, `docs/2026-07-20-diverse-reach-transfer.md`). The honest RF baseline:

| Held-out fold | Morphology | RF median-mosaic AUC |
|---|---|---|
| Farmington | wide river | 0.905 |
| Aztec/Animas | tributary | 0.886 |
| Kirtland | mainstem | 0.845 |
| **Malpais** | **arroyo** | **0.557** |
| **macro-mean** | — | **0.798** |

Pooling diverse reaches closes river-corridor transfer to ~0.88; the arroyo stays 0.557 because it is the
sole example of its type. **That gap is the FM's opening** — and the number it must beat.

## Acceptance contract (both models, identical footing)

The FM's prediction is scored against the RF numbers above under these **reproducible** rules. No
qualitative language decides the gate.

**1. Transfer — the primary criterion.** Metric: LORO held-out-reach **ROC-AUC** on the extent task, per
fold and macro-mean. Significance via **DeLong 95% CI** on the paired FM−RF AUC difference (same held-out
pixels, so paired). A fold *passes* iff the FM−RF difference CI lower bound **> 0**. The FM clears Transfer
iff **either**:
  - **(a) broad win** — macro-mean AUC improvement **≥ +0.04** (FM macro-mean **≥ 0.838**) **and** the
    macro-mean improvement is significant (paired CI excludes 0); **or**
  - **(b) arroyo win** — the **Malpais fold** improves by **≥ +0.04** (FM **≥ 0.597**), significant by
    DeLong, **and** no other fold regresses by **> 0.01 AUC**. This is the pre-flight's exact prediction —
    a win confined to the hard, under-represented morphology still counts, and is the more *interesting*
    result.

**2. Coherence — the secondary criterion, at matched recall.** First fix the operating point: threshold
each model's probability field per held-out reach so **recall on held-out positives = 0.80** (identical
recall removes the "cleaner because it predicts less" confound). At that threshold, compute:
  - **Speckle** — fraction of predicted-positive pixels with **no 4-connected positive neighbour**. FM must
    be **≤ 0.5× RF's**.
  - **Connectivity** — **largest-connected-component share** of predicted-positive area. FM must be
    **≥ RF's + 0.10**.
  - **Moran's *I*** of the probability field (spatial autocorrelation). FM must be **≥ RF's**.

  Coherence *passes* iff **≥ 2 of these 3** clear their thresholds. This is what replaces "materially
  cleaner."

**3. Calibration — a guard, not a gate.** Metric: **Expected Calibration Error** (ECE, 10 equal-width
bins) on the held-out reach. FM ECE must be **≤ RF ECE + 0.02**. A larger regression does **not** by
itself abort — a transfer-winning FM can be recalibrated (isotonic/Platt) before ship — but it is
**flagged as required recalibration work**, not waved through.

A **visual side-by-side** (FM vs RF extent over each held-out reach, on NAIP, at the matched-recall
threshold) accompanies the numbers, because the coherence claim is ultimately a product-quality claim.

## Why 1.1 specifically

v1.1 is **~3× fewer tokens** than v1.0 at parity quality (Phase-0 finding), which for **batch inference
across the basin** is real deployment economics — the difference between a demo and an archive roll-out.
v1.0's only edge was that it resolves in the pinned stack; **1.1 needs `olmoearth_pretrain ≥ 0.1.1`
(breaks the runner pin) and its HF weights are gated (401)**. Resolving those is in-scope here — the
efficiency is the deploy-time reason to pay that cost now (it was explicitly parked "for Phase 3").

## Go / abort — written before the spend

Decided on the **extent task only**, against the measured RF bar (macro-mean 0.798; arroyo 0.557):

- **GO (FM ships for the map):** **Transfer passes** — criterion **(a)** *broad win* (macro-mean ≥ 0.838,
  significant) **or** **(b)** *arroyo win* (Malpais ≥ 0.597, significant, no other fold −0.01) — **OR**
  Transfer is a statistical tie **and Coherence passes** (≥ 2 of 3 at matched recall) with no fold
  regressing significantly. Calibration must not be flagged, or its recalibration work is scoped into the
  ship. A Transfer win **and** Coherence pass is the strong case.
- **ABORT (RF ships):** Transfer fails **both** (a) and (b) — macro-mean improvement < +0.04 or its CI
  includes 0, **and** the arroyo fold does not clear (b) — **and** Coherence fails (< 2 of 3). Then RF is
  the deploy model, the map gets cheap morphological cleanup, and we record — with a number — that the FM
  did not earn it here either. **That is a publishable result, not a failure.**
- **Cost guard:** the median-mosaic data build + RF baseline are **laptop/$0 and already done** (PR #71).
  Only now does the GPU come out of hibernation for the FM fine-tune (control-run scale, the 4-reach set —
  a few dollars, per the [GPU plan](2026-07-12-gpu-finetune-execution-plan.md)).

## Sequence

1. **$0, laptop — DONE (PR #71):** median-mosaic cubes for the 4 diverse reaches, LORO median-mosaic RF,
   transfer AUC table (macro-mean 0.798). **This is the bar.** Still to add on the FM run: the coherence
   metrics + calibration at matched recall on the same folds (the RF side of those tables is computed in
   the same harness when the FM prediction lands).
2. **$0, laptop:** resolve the OlmoEarth 1.1 stack (`olmoearth_pretrain ≥ 0.1.1`, HF gate) and dry-run
   the fine-tune config on CPU/NANO — no GPU yet.
3. **~$3–15, GPU:** fine-tune OlmoEarth 1.1 on the same pooled reaches; predict the held-out reach;
   score against the bar. Apply go/abort.
4. **Ship the winner** as the deployable map's model — into `silver.riparian_extent` for the interactive
   map and baked into the static GitHub-Pages twin.

The point is not to make the FM win. It is to give it the one fair chance to, on the axis that actually
decides a deployed product — and to ship whichever model the number picks.
