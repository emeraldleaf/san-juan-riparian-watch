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
from 0.37 to 0.80. **Step 0 of this experiment is to rebuild the RF baseline on median mosaics.** The
FM must beat *that*, not the strawman.

## What gets measured (both models, identical footing)

Train on **N pooled NM reaches** (Farmington + Malpais + ≥1 more), predict a **held-out reach**, on
identical aligned median-mosaic cubes:

| Claim | Metric | FM must show |
|---|---|---|
| **Transfer** | held-out-reach AUC (rotate each reach out) | **≥ +0.04 over median-mosaic RF** (the pre-flight's own predicted margin) |
| **Coherence** | edge/speckle: fraction of isolated single-pixel predictions; corridor connectivity (largest-component share); Moran's *I* of the probability field | **materially cleaner** than RF at matched recall — quantified, not eyeballed |
| **Calibration** | reliability curve on held-out reach | no worse than RF |

A **visual side-by-side** (FM vs RF extent over the held-out reach, on NAIP) accompanies the numbers —
because the coherence claim is ultimately a product-quality claim.

## Why 1.1 specifically

v1.1 is **~3× fewer tokens** than v1.0 at parity quality (Phase-0 finding), which for **batch inference
across the basin** is real deployment economics — the difference between a demo and an archive roll-out.
v1.0's only edge was that it resolves in the pinned stack; **1.1 needs `olmoearth_pretrain ≥ 0.1.1`
(breaks the runner pin) and its HF weights are gated (401)**. Resolving those is in-scope here — the
efficiency is the deploy-time reason to pay that cost now (it was explicitly parked "for Phase 3").

## Go / abort — written before the spend

- **GO (FM ships for the map):** FM beats median-mosaic RF by **≥ +0.04 AUC on held-out-reach transfer**
  **OR** delivers materially cleaner maps (speckle ↓, connectivity ↑) at matched recall with no AUC
  regression. Either alone justifies it for the *map product*; both is the strong case.
- **ABORT (RF ships):** FM ties or trails median-mosaic RF on transfer **and** shows no coherence edge.
  Then RF is the deploy model, the map gets cheap morphological cleanup, and we record — again, with a
  number — that the FM did not earn it here either. That is a publishable result, not a failure.
- **Cost guard:** the median-mosaic data build + RF baseline are **laptop/$0** and happen first. Only
  after the RF baseline is in hand does the GPU come out of hibernation for the FM fine-tune (control-run
  scale, single reach-set — a few dollars, per the [GPU plan](2026-07-12-gpu-finetune-execution-plan.md)).

## Sequence

1. **$0, laptop:** rebuild median-mosaic cubes for the train reaches + a held-out reach
   (`materialize_reach.py` compositing, not `deploy_extent_map.py`'s single-scene fetch); train
   median-mosaic RF; record transfer AUC + coherence metrics + the visual. **This is the bar.**
2. **$0, laptop:** resolve the OlmoEarth 1.1 stack (`olmoearth_pretrain ≥ 0.1.1`, HF gate) and dry-run
   the fine-tune config on CPU/NANO — no GPU yet.
3. **~$3–15, GPU:** fine-tune OlmoEarth 1.1 on the same pooled reaches; predict the held-out reach;
   score against the bar. Apply go/abort.
4. **Ship the winner** as the deployable map's model — into `silver.riparian_extent` for the interactive
   map and baked into the static GitHub-Pages twin.

The point is not to make the FM win. It is to give it the one fair chance to, on the axis that actually
decides a deployed product — and to ship whichever model the number picks.
