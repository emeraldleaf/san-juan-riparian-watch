# Label-budget sweep — testing the label-efficiency hypothesis (and mostly rejecting it)

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Tiles:** Malpais + Animas, NM ·
Follows the [cross-tile transfer result](2026-07-16-cross-tile-transfer-results.md).

## The hypothesis under test
The transfer result showed a +0.070 Presto-over-RF edge in one condition (train species on
label-scarce Animas, test Malpais) and proposed the label-efficiency law behind it:
> *"The foundation model should beat RF **most where labels are thinnest** — and that advantage
> should **widen as labels shrink**."*
If true, that widening curve *is* the GPU business case. This sweep tests it directly: train species
classification at budgets of 50–3200 labeled px/class, measure the RF-vs-Presto cross-tile ROC-AUC
gap at each budget, 8–10 random label draws per point for error bars.

## Result: the hypothesis is NOT supported

| Direction | Budget range | RF ROC | Presto ROC | Gap vs. budget |
|---|---|---|---|---|
| Train Malpais (rich) → test Animas | 50 → 3200 | 0.72–0.73 | 0.71–0.73 | **flat ≈ 0**, slightly RF-favoring at high budget |
| Train Animas (scarce) → test Malpais | 50 → 400 | 0.66–0.68 | 0.69–0.71 | **flat ≈ +0.03**, does not widen |

**The gap is flat against label count in both directions.** Presto's edge does not grow as labels
shrink — the defining prediction of the label-efficiency hypothesis fails. At large budgets in the
label-rich direction the gap even turns slightly negative (RF wins by ~0.02 at 3200/class).

## What is actually there — a smaller, different effect

There is a **real but modest, direction-dependent** edge: **Presto beats RF by ~+0.03 ROC whenever
Animas is the training tile** (test Malpais), consistently across every budget (50→400 px). It is
not a label-count effect and not a single-point artifact (stable over 10 draws at 4 budgets). It is a
**transfer-direction** effect: the pretrained representation generalizes from the agricultural/
developed Animas tile to the lowland-alluvial Malpais tile better than hand-features do, while in the
reverse direction both are equivalent.

This also **partly retracts** the earlier +0.070 headline: at matched budgets the Animas→Malpais edge
is +0.025–0.035, not +0.070. The larger prior number came from a single all-data draw and sat within
the noise this sweep now quantifies. **Corrected effect size: ~+0.03 ROC, direction-dependent.**

## What this means for the OlmoEarth decision — honest revision

- **The clean GPU business case (a widening label-efficiency curve) did not materialize.** On this
  data, at this scale, with frozen Presto, the FM does not do the one thing that most cleanly
  justifies its cost. This is the most important negative result in the project so far, and it should
  temper the GPU case, not inflate it.
- **A weaker case survives:** a consistent ~+0.03 ROC transfer-direction edge. Whether that is worth
  a GPU depends on whether it (a) holds for OlmoEarth-Base (207M params may show a larger effect than
  0.82M Presto), (b) compounds across many reaches at basin scale, and (c) survives fine-tuning. None
  of those is established; all are +0.03-sized bets, not +0.10 ones.
- **The decisive experiments are now clear, and two are still CPU/$0:**
  1. **Fine-tune Presto** in the Animas→Malpais direction — does adapting (not just reading) the
     representation turn +0.03 into something larger? If frozen +0.03 is the ceiling, the GPU case is
     weak; if fine-tuning materially widens it, that motivates the bigger model.
  2. **More tiles / true label diversity** — two tiles cannot separate "transfer-direction effect"
     from "Animas-specific quirk." The third dev tile (Turkey Creek) or additional reaches would test
     whether the ~+0.03 is a general Animas-as-source property or noise.
  3. **(GPU) OlmoEarth-Base at matched budgets** — only worth doing *after* 1–2 show the effect is
     real and scales; otherwise it is renting a GPU to confirm a +0.03 that a free 0.82M model
     already found.

## Honest caveats
- Frozen Presto only; fine-tuning untested (item 1 above).
- Two tiles; the direction effect could be an Animas idiosyncrasy (item 2).
- Species task, S2-subset+NDVI, 2020, 20 m — same envelope as prior results.
- Animas introduced pool is 598 px, capping the scarce-direction budget at 400/class.

## Reproducibility
`bench_sweep.py` (Malpais→Animas), `bench_sweep_rev.py` (Animas→Malpais),
`bench_sweep_results.json`, `bench_sweep_rev_results.json`.
