# Fine-tune transfer — is the frozen +0.03 a floor or a ceiling? (It's a floor.)

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Direction:** Animas → Malpais (label-scarce),
species task · Follows the [label-budget sweep](2026-07-16-label-budget-sweep-results.md).

## The question
The sweep left one decisive cheap test: the frozen Presto edge was ~+0.03 ROC and flat vs. budget.
Is that the **ceiling** of what the pretrained representation can do (→ weak GPU case), or a **floor**
that *fine-tuning* — actually adapting the encoder, not just reading it — can widen (→ real GPU case)?
This runs RF vs frozen-Presto vs **fine-tuned-Presto**, same Animas→Malpais transfer, 2 budgets, 5
label draws each.

## Result: fine-tuning widens the edge — it's a floor

| Budget (px/class) | RF | Presto frozen | Presto **fine-tuned** | frozen edge | **FT edge** |
|---|---|---|---|---|---|
| 100 | 0.688 ± 0.037 | 0.733 ± 0.029 | **0.752 ± 0.024** | +0.045 | **+0.064** |
| 400 | 0.671 ± 0.015 | 0.701 ± 0.012 | **0.754 ± 0.021** | +0.030 | **+0.083** |

Three things move in the right direction at once:
1. **Fine-tuning beats frozen** at both budgets (+0.019 at 100, **+0.053 at 400**) — adapting the
   representation extracts signal the frozen readout leaves on the table.
2. **The fine-tuned edge over RF grows with budget** (+0.064 → +0.083), while the *frozen* edge
   *shrank* with budget (+0.045 → +0.030). Fine-tuning reverses the sign of the budget trend.
3. **Fine-tuned Presto is budget-stable** (0.752 → 0.754) while RF drifts *down* (0.688 → 0.671) —
   RF overfits the small Animas training sample to Animas-specific cues that don't transfer; the
   fine-tuned FM does not.

## What this means for the OlmoEarth decision — the case is now real

- **The GPU hypothesis flipped from "weak" to "supported."** The prior sweep rejected the clean
  label-efficiency law and left only a modest frozen +0.03. Fine-tuning turns that into **+0.06 to
  +0.08 ROC on the label-scarce transfer that is the whole point of a basin-scale product** — and the
  advantage is largest exactly where deployment lives (few labels, new ground).
- **This is the mechanism the ADR bet on.** The plan of record fine-tunes OLMOEARTH_V1_BASE (not a
  frozen readout). This result — on a 0.82M-param stand-in, on CPU — is the first direct evidence that
  the *fine-tuning* step, not the model per se, is where the value is. It de-risks the GPU spend: the
  thing you're paying to do is the thing that works.
- **Concrete expectation to hold OlmoEarth-Base to:** on Animas→Malpais species at ~100–400 labels,
  beat RF by **≥ +0.06 ROC after fine-tuning**, and beat *fine-tuned Presto* (0.75) by enough to
  justify 250× the parameters and the GPU. If OlmoEarth-Base can't clear fine-tuned Presto, rent the
  GPU for nothing — a $0 CPU model already got there.

## Honest caveats (these matter)
- **Error bars overlap.** At 5 seeds the SDs (0.01–0.04) mean the +0.019 frozen→FT gain at budget 100
  is *within noise*; the +0.053 gain at budget 400 and the FT-vs-RF gaps are the robust signals. Read
  the **budget-400 column** as the load-bearing result, not budget-100.
- **Two tiles, one direction, one year.** The effect is Animas→Malpais; Malpais→Animas showed no
  frozen edge (sweep), so this is *not* symmetric and could carry an Animas-as-source idiosyncrasy.
  More tiles remain the key missing control.
- **598 introduced px cap** the Animas budget at 400/class; a larger invasives label set (ADR cites
  ~332 polygons basin-wide) would tighten every point.
- Frozen and FT both use S2-subset+NDVI (S1/ERA5/SRTM masked); the light CPU fine-tune (15 epochs,
  fixed LR) is a lower bound on what a proper GPU recipe achieves.
- Not threshold-calibrated (ROC-AUC is threshold-free, so this is clean); F1 would need per-tile
  recalibration as before.

## Bottom line across all five benchmarks
1. Extent in-tile: RF = Presto (task saturated).
2. Species in-tile: RF = Presto (hard task, no FM edge).
3. Cross-tile transfer: works for both; FM edge only in label-scarce direction.
4. Label-budget sweep: FM edge does NOT widen as labels shrink (frozen); ~+0.03 direction effect.
5. **Fine-tune transfer: fine-tuning widens the edge to +0.06–0.08 — the GPU case, finally supported.**

The through-line: **the FM earns its keep only when (a) you fine-tune it and (b) you deploy it on
label-scarce, unseen ground** — which is exactly the annual-basin-product setting, and exactly what
the ADR planned. Extent and single-tile accuracy were never the place to look.

## Reproducibility
`bench_ft_transfer.py`, `bench_ft_transfer_results.json`.
