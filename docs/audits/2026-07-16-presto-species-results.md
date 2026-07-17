# Species-split result — Presto vs RF on introduced-vs-native woody (Malpais)

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Tile:** Malpais (140801051001, NM) ·
Companion to [the extent result](2026-07-16-presto-arm-results.md) and the
[bench spec](specs/2026-07-16-three-way-extent-bench.md).

## Why this task
Extent turned out saturated by simple features (all arms ~0.80 F1). The mechanistic case for a
temporal foundation model — late-season senescence phenology separates Tamarix/Russian olive from
native cottonwood/willow — applies to the **species** task, not extent. This runs that test: the
within-corridor introduced-vs-native discrimination, the actual scientific contribution.

## What ran
Same harness, same frozen spatial folds (`assign_spatial_folds` 0.02° → GroupKFold, 22 blocks → 5
folds). 12,000 balanced woody-riparian pixels (**6,000 introduced / 6,000 native**), from NMRipMap
2020 (299 introduced/IC polygons, 328 native woody). Sentinel-2 2020, 12 monthly composites, 20 m.
Fine-tune arm now uses **threshold selection on an inner-validation split** (fixing the Arm-B2
extent collapse).

| Arm | Model | F1 | PR-AUC | ROC-AUC | Per-fold F1 |
|---|---|---|---|---|---|
| A | RF, temporal features | 0.667 | **0.732** | 0.735 | 0.54–0.76 |
| B | Presto frozen + RF | 0.674 | 0.717 | **0.742** | — |
| B2 | Presto fine-tuned (calibrated) | **0.677** | 0.686 | 0.723 | 0.60–0.80 |

## Two findings

**1. Species discrimination is genuinely hard at 10–20 m with these labels.** Every arm falls from
~0.80 F1 / ~0.89 ROC (extent) to **~0.67 F1 / ~0.73 ROC** (species). That is the real difficulty of
the contribution, quantified: separating introduced from native woody riparian from optical
phenology alone is a ROC-0.73 problem on this tile, not a solved one.

**2. The foundation model gives no edge — even here, even fine-tuned.** RF 0.667, Presto frozen
0.674, Presto fine-tuned 0.677. The spread (0.010 F1) is within fold noise, and the three arms
trade rank across PR-AUC / ROC. Fine-tuning the FM end-to-end did **not** unlock the phenology
signal beyond what RF's temporal features already capture. This is now consistent across **both
tasks and all three approaches**.

## What this means for the OlmoEarth decision

- **The GPU case is now weak on evidence, not opinion.** A 0.82 M-param FM, frozen *and* fine-tuned,
  ties RF on the exact task where an FM was supposed to win. For OlmoEarth-Base (207 M params, GPU) to
  be worth it, it must beat ~0.67 F1 / ~0.74 ROC on these folds by a margin a 250×-smaller FM could
  not reach. That is a specific, falsifiable bar — and the burden of proof now sits with the FM.
- **This does not kill the contribution — it relocates it.** The value may not be "FM > RF on a
  single 2020 tile," but the **annual time axis** (nobody has a per-year introduced-vs-native product
  for this basin) and **better labels / more signal**, not a bigger model. Three concrete levers the
  bench points to, all cheaper than GPU:
  1. **Add the senescence-window channel** (Sep–Oct contrast) explicitly — the phenology literature
     says the signal is there; neither RF temporal stats nor frozen Presto is being handed it directly.
  2. **Add S1 SAR + terrain** — Presto ran with S1/ERA5/SRTM masked (unavailable locally). Structure
     and moisture may carry the introduced/native difference optical bands miss.
  3. **The defoliation confound** (CSU live/dead/defoliated points) — some "native-looking" browning
     is beetle-defoliated Tamarix; cleaning that may raise every arm's ceiling.
- **Recommended gate before renting a GPU:** re-run this exact three-arm bench *after* adding the
  senescence channel + S1. If RF closes most of the gap to any FM with those cheap additions, the GPU
  is not the bottleneck — the features and labels are.

## Honest caveats
- One tile. Animas (the ADR's primary invasives tile, ~332 IC polygons) is the necessary second run.
- Presto used S2-subset + NDVI, S1/ERA5/SRTM masked; a fuller input could help it (and RF).
- NMRipMap 2020 introduced/native boundaries are the ground truth; polygon-edge mixed pixels add
  noise to a hard task (all-touched rasterization is inclusive).
- Fine-tune is a light CPU recipe (10 epochs, threshold-calibrated); not an exhaustive search, but
  the frozen and fine-tuned arms agree, which bounds the upside.

## Reproducibility
`lab_species.py` (labels), `bench_species.py` (Arms A/B), `bench_species_ft.py` (Arm B2),
`bench_species_results.json`, `malpais_species_px.npz`, shared `malpais_raw_bandcube.npz`.
