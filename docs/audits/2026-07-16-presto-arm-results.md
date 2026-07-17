# Arm B result — Presto vs RF on Malpais extent (the FM-earns-its-GPU pre-test)

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Tile:** Malpais (140801051001, NM) ·
**Bench spec:** [three-way-extent-bench](specs/2026-07-16-three-way-extent-bench.md).

## What ran
Two of the three arms from the bench spec, on **identical pixels and identical frozen spatial folds**
(`assign_spatial_folds`, 0.02° blocks → GroupKFold, 24 spatial blocks → 5 folds). 12,000 balanced
labeled pixels (6,000 woody-riparian pos / 6,000 real-NMRipMap-class neg — **not** arbitrary desert
negatives). Labels: NMRipMap 2020 (627 woody-riparian polygons incl. **299 introduced/Tamarix–Russian
olive**, 340 negative-class). Imagery: Sentinel-2 2020, 12 monthly median composites, 20 m.

| Arm | Model | F1 (5-fold) | PR-AUC | ROC-AUC | Per-fold F1 |
|---|---|---|---|---|---|
| **A** | RF on temporal features (median/p10/p90/amplitude × 11 bands) | **0.804** | 0.902 | 0.885 | — |
| **B** | Presto **frozen** embeddings (0.82 M params) + RF head | **0.803** | 0.901 | 0.886 | — |
| B2 | Presto **fine-tuned** end-to-end (naive, CPU) | 0.664* | 0.887 | 0.871 | 0.60–0.75 |

\* Arm B2 shows a **threshold collapse** (precision 0.50 / recall 1.00 at 0.5 — predicts all-positive)
despite healthy PR-AUC 0.887. That is a calibration artifact of an under-tuned CPU fine-tune (fixed
LR, 8 epochs, no class-balanced sampling or threshold selection), **not** a signal failure — the
ranking metrics are fine. **Arm B (frozen) is the fair, stable Presto number.**

## The finding

**A frozen foundation model ties hand-engineered features almost exactly** — F1 0.803 vs 0.804,
PR-AUC 0.901 vs 0.902, ROC 0.886 vs 0.885. The difference is within fold noise. On *this* task
(riparian extent, Malpais, 2020), Presto's pretraining buys **nothing measurable** over the RF the
project already has.

This is the **`Tong2025_CropGlobe` result reproduced on San Juan data**: simple spectral-temporal
representations match modern geospatial-FM embeddings. It also rhymes with the retracted frozen-Nano
result — except this time the harness is correct (real folds, real negatives, year-matched labels,
proper per-pixel scoring), and the FM still doesn't win.

## What this means for the OlmoEarth decision

1. **The bar for OlmoEarth-Base just got concrete and high.** To justify its GPU, OlmoEarth-Base must
   beat **~0.80 F1 / ~0.90 PR-AUC on these exact folds** — not the retracted 0.065, and not the
   patch-level 0.701. If a 0.82 M-param model pretrained on global EO ties RF, a 207 M-param model
   has to demonstrate it earns 250× the parameters and the GPU rental.
2. **Extent is very likely not where OlmoEarth wins** — consistent with the ADR demoting extent to a
   *calibration control*. The result strengthens that call: extent is saturated by simple features.
3. **The real test is the species/phenology split, not extent.** The mechanistic argument for the FM
   (late-season senescence is a temporal pattern) applies to the Tamarix-vs-native task, which this
   bench did not run. **Recommendation: port this exact harness to the introduced-vs-native woody
   labels (299 IC polygons here) before spending GPU on extent** — if the FM can't beat RF on
   *species* either, the GPU case weakens sharply; if it can, that's the defensible contribution.

## Honest caveats
- One tile (Malpais). Should be repeated on Animas before generalizing.
- Presto uses an S2-subset + NDVI with S1/ERA5/SRTM channels masked (we don't have them locally); a
  fuller input might help it — but that is also true of any cheap deployment, which is the point.
- Arm B2's fine-tune deserves one more pass with class-balanced sampling + threshold tuning before
  being cited as Presto's ceiling; the frozen number is the safe one.
- Presto full-text not yet read (arXiv unreachable in-session); architecture used as-shipped.

## Reproducibility
`bench.py` (Arms A/B), `bench_ft.py` (Arm B2), `bench_results.json` (metrics),
`malpais_raw_bandcube.npz` (12-month raw bands), `malpais_labeled_px.npz` (labels).
Presto install: see `PRESTO_SETUP.md` + `presto_working_install.tar.gz`.
