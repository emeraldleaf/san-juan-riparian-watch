# Cross-tile transfer — the test that matches the actual goal

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Tiles:** Malpais (140801051001) + Animas/Tucker
Canyon (140801041003), NM · Companion to [extent](2026-07-16-presto-arm-results.md) and
[species](2026-07-16-presto-species-results.md) results.

## The goal this tests
> *"Can I map the whole San Juan basin — or years and reaches with no NMRipMap labels — without
> hand-labeling each one?"*

The in-tile benchmarks held RF and Presto at equal footing (same tile, dense labels) and they tied —
the fair test for *accuracy*, but the wrong test for *this goal*. The goal is **transfer**: train where
labels exist, predict where they don't. So this trains each model on one tile and scores it on the
**other, entirely held-out** tile (~150 km away, different valley morphology), against that tile's own
2020 NMRipMap labels. The question is not "who is more accurate" but **"who degrades less on ground it
never trained on."**

## Results (ROC-AUC — the fair, threshold-free metric)

| Task | Direction | RF | Presto frozen | Winner |
|---|---|---|---|---|
| Extent | in-tile (Malpais CV) | 0.885 | 0.886 | tie |
| Extent | Malpais → Animas | 0.803 | 0.805 | tie |
| Extent | Animas → Malpais | 0.793 | 0.804 | tie (Presto +0.011) |
| Species | in-tile (Malpais CV) | 0.735 | 0.742 | tie |
| Species | Malpais → Animas | 0.742 | 0.727 | tie (RF +0.015) |
| Species | **Animas → Malpais** | **0.652** | **0.722** | **Presto +0.070** |

## Three findings

**1. Transfer works — and it's the good news.** ROC-AUC barely moves under cross-tile transfer for
extent (0.89 in-tile → 0.79–0.81 cross-tile) and holds for species (~0.73). A model trained on one
reach *does* carry to another. This is the core evidence that a labeled-tile → unlabeled-basin workflow
is viable at all — for **either** model. That matters more than which model wins: the basin-scale
ambition is not blocked by catastrophic transfer failure.

**2. RF and Presto tie on transfer too — except in the label-scarce direction.** In 5 of 6 conditions
the two are within fold noise. The **one exception is the tell**: training species on **Animas** (which
has only 19 introduced polygons / 598 px) and testing on Malpais, RF drops to ROC 0.652 while Presto
holds 0.722 — a **+0.070 FM edge**. This is the label-efficiency axis showing up exactly where theory
predicts: when labels are scarce, the pretrained representation degrades more gracefully than
hand-features fit to a thin sample. It is the first signal in this whole project that the FM does
something RF can't — and it appears only under label scarcity, which is precisely the basin-scale
condition.

**3. F1 collapses under transfer, but that's a red herring.** F1 at a fixed 0.5 threshold falls hard
(e.g. extent A→M: RF 0.60, Presto 0.39) while ROC stays ~0.80. That gap is **threshold
miscalibration** — the decision cutoff tuned to one tile's class balance is wrong for another's — not a
representation failure. The ranking is intact; only the operating point moved. Any deployment must
recalibrate the threshold per tile (or use a class-balance prior), which is cheap. Do **not** read the
F1 collapse as "transfer doesn't work."

## What this means for the OlmoEarth decision

- **The FM's value proposition is now located precisely.** It is not accuracy on a labeled tile
  (tie), and not even transfer accuracy in general (tie). It is **transfer under label scarcity** —
  the +0.070 species A→M edge. That is the same axis that made OlmoEarth worth it for Global Mangrove
  Watch (10k labels beating a 5.8M-sample pipeline), reproduced in miniature on San Juan data.
- **This is now the defensible GPU hypothesis:** OlmoEarth-Base should beat RF *most* where labels are
  *thinnest* — the un-labeled reaches and years that are the entire point of the basin-scale product.
  A 0.82M-param Presto already shows the effect; a 207M-param model pretrained on more EO data is the
  natural place to test whether the effect grows.
- **Concrete pre-GPU gate:** the Animas→Malpais species result is real but **underpowered** (598
  introduced px). Before spending GPU, repeat the label-scarce transfer test with (a) the full Animas
  invasives labels (ADR cites ~332 polygons basin-wide vs 19 in this dev tile) and (b) a deliberate
  label-budget sweep (train on 100 / 300 / 1000 / all introduced px, measure the RF-vs-Presto gap as a
  function of label count). If the FM's advantage widens as labels shrink, that curve *is* the GPU
  justification.

## Honest caveats
- **Spatial transfer only.** Both tiles have 2020 labels, so cross-*tile* transfer is scorable.
  **Temporal** transfer (other years) has no labels anywhere to score against — it remains an
  inference, not a measurement. The annual-product claim rests on spatial transfer generalizing to
  time, which this cannot prove.
- **Species A→M is underpowered** (598 introduced px on Animas); treat the +0.070 as indicative,
  worth confirming, not a settled number.
- Two tiles, one year, S2-subset + NDVI (S1/ERA5/SRTM masked). Presto might gain more from the full
  input stack it was designed for.
- Frozen Presto only here (fine-tuning per direction was out of scope); frozen is the conservative
  estimate of the FM's transfer.

## Reproducibility
`rawcube_animas.py`, `lab_animas.py`, `bench_transfer.py`, `bench_transfer_results.json`,
`animas_raw_bandcube.npz`, `animas_extent_px.npz`, `animas_species_px.npz`.
