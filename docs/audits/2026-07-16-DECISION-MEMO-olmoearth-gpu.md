# Decision memo — should we rent a GPU and fine-tune OlmoEarth for the San Juan riparian product?

**Date:** 2026-07-16 · **Author:** external Claude Science session (CPU-only) · **Status:** recommendation, for the repo agent + PI
**TL;DR:** **Yes, conditionally.** Six CPU benchmarks converge on one finding: a fine-tuned temporal
foundation model beats the RF baseline **only** when transferring from a hard/label-scarce reach to
unseen ground (+0.04 to +0.08 ROC), and ties RF everywhere else. That transfer setting *is* the
annual-basin-product goal, so the GPU is justified — but OlmoEarth-Base must clear a concrete bar
(below), and the six caveats in §5 must travel with every number.

> **Read-me-first for the repo agent:** these are **CPU pre-flight results on a 0.82 M-param stand-in
> (Presto), not settled OlmoEarth numbers.** They tell you *where to look and what bar to beat*, not
> what OlmoEarth will score. Honor §4 (frozen decisions) and §5 (caveats) or the GPU run inherits
> false confidence. Nothing here was committed to the repo; treat as additive `docs/audits/` material.

> ## 🔴 Correction on landing (repo agent, 2026-07-17) — §1 and §7.2 are not executable as written
>
> **`OLMOEARTH_V1_1_BASE` does not exist in the pinned stack.** This memo was written in an external
> session with no installed stack, so it could not have known. Phase 0 verified it mechanically on
> 2026-07-13: `olmoearth-runner==0.1.14` pins `rslearn==0.0.27`, whose `ModelID` enum has exactly
> four members — `OLMOEARTH_V1_{NANO,TINY,BASE,LARGE}`. There is no v1.1. Re-verified on landing.
>
> **This changes the cost model, which §7.4 inherits from the ADR.** Measured on this exact config
> (32×32 window, 12 monthly mosaics, `patch_size: 2`): **v1-Base emits 9,216 tokens/window vs v1.1's
> 3,072**. Attention is O(n²), so the "$2–5 control / $30–60 total" figure assumed v1.1 and is
> roughly **3× optimistic on v1** — which **may also not fit 24 GB at batch 8** (batch 4 + AMP).
>
> Two options, both decidable on a laptop for $0 *before* renting anything:
> 1. Use **`OLMOEARTH_V1_BASE`** and re-cost at ~3×; or
> 2. Try unpinning `rslearn` for a v1.1-wired release — which breaks the `olmoearth-runner` pin and
>    is its own Phase-0 exercise, not a GPU-clock discovery.
>
> Everything else in this memo stands: the six-benchmark arc was verified against the raw
> `bench_*_results.json` on landing and the decisive three-tile table reproduces exactly.
> **§6's bar also settles the repo's open decoder decision** — the bar is *pixel-level* ROC at
> 100–400 px/class, and the scaffold's `SegmentationPoolingDecoder` emits one prediction per window
> broadcast to all pixels, so it **cannot be scored against this bar at all**. `UNetDecoder` is now
> required to measure the thing this memo defines, not merely preferred. See
> [`../2026-07-14-phase-0-record.md`](../2026-07-14-phase-0-record.md).

---

## 1. The question and the answer
Does a geospatial foundation model (**OLMOEARTH_V1_1_BASE**, 207.5 M params — the ADR predates the
v1.1 checkpoint and names it `OLMOEARTH_V1_BASE`; use v1.1, fine-tuned per the `mangrove` recipe)
earn its GPU over the existing RandomForest baseline for **riparian extent** and **Tamarix/Russian-olive
species mapping** across the San Juan basin over time?

**Answer:** Not for extent (RF already solves it). Not for single-tile accuracy (FM ties RF). **Yes for
the one thing that defines the contribution** — mapping label-scarce, unseen reaches/years by
transferring from a few labeled reaches — *if* fine-tuned. That is a +0.04–0.08 ROC effect on a tiny
stand-in model; the bet is that OlmoEarth-Base amplifies it.

## 2. The six-benchmark arc (all CPU, $0, Sentinel-2 2020, 20 m, species = introduced-vs-native woody)

| # | Benchmark | Result | Takeaway |
|---|---|---|---|
| 1 | Extent, in-tile (Malpais spatial CV) | RF F1 0.804 / ROC 0.885; Presto-frozen F1 0.803 / ROC 0.886 | **Tie** — extent saturated by simple features |
| 2 | Species, in-tile (Malpais spatial CV) | RF F1 0.667 / ROC 0.735; Presto-frozen F1 0.674 / ROC 0.742; Presto-FT F1 0.677 | **Tie** — hard task (ROC ~0.74), no FM edge in-tile |
| 3 | Cross-tile transfer (Malpais↔Animas) | ROC holds (extent 0.79–0.81, species ~0.73); FM edge only Animas→Malpais species (+0.070 raw) | Transfer works for both models; F1 collapse = threshold miscalibration, not representation failure |
| 4 | Label-budget sweep (frozen) | Gap flat vs. label count in both directions; ~+0.03 direction effect, does NOT widen as labels shrink | Clean label-efficiency law **rejected**; +0.070 corrected to +0.025–0.035 |
| 5 | Fine-tune transfer (Animas→Malpais) | RF 0.671 → Presto-FT 0.754 @ 400 px/class (**+0.083**); +0.064 @ 100 px | **Fine-tuning is a floor, not a ceiling** — adapting the encoder widens the edge |
| 6 | **Three-tile transfer** (+Bloomfield) | FT Presto beats RF in **5 of 6** directed transfers; edge +0.076/+0.058/+0.036 where RF worst, ~0 where RF good | **Edge generalizes and is lawful** — largest exactly where RF fails to transfer |

**Through-line:** *Fine-tune the FM + deploy on hard/label-scarce unseen ground → +0.04–0.08 ROC.
Anywhere else (extent, in-tile, easy transfer) → use RF.* The FM's value is transfer under scarcity,
not accuracy on a labeled tile — which is why the ADR correctly demotes extent to a calibration control.

## 3. Three-tile transfer detail (benchmark 6, the decisive control)

| Transfer (train→test) | RF ROC | Presto FT ROC | Edge |
|---|---|---|---|
| Animas → Malpais | 0.670 | 0.746 | **+0.076** |
| Animas → Bloomfield | 0.676 | 0.734 | **+0.058** |
| Bloomfield → Malpais | 0.728 | 0.764 | **+0.036** |
| Malpais → Animas | 0.733 | 0.748 | +0.015 |
| Bloomfield → Animas | 0.728 | 0.743 | +0.015 |
| Malpais → Bloomfield | 0.735 | 0.729 | −0.006 |

*(species, 400 labeled px/class, mean of 3 seeds. Note: Turkey Creek could NOT be a third tile —
NMRipMap is NM-only, returns 0 polygons in CO. Substituted San Juan @ Bloomfield NM: same label
source, spatially independent, 13,094 introduced px vs Animas's 598.)*

The edge scales inversely with RF's transfer skill: +0.06–0.08 where RF is stuck at ~0.67, →0 where RF
already reaches ~0.73. This is the label-efficiency/transfer axis behaving as theory predicts, and it
reproduces on the independent Bloomfield tile — so it is **not an Animas artifact**.

## 4. Frozen decisions the GPU run MUST honor (from the ADR + these results)
1. **Fit-year = 2020** (NMRipMap v2.0 Plus labels are NAIP-2020; imagery must match — the retracted
   fair-test used 2024 and was wrong).
2. **Three NM tiles, one label source (NMRipMap):** Malpais (140801051001), Animas/Tucker Canyon
   (140801041003), Bloomfield (San Juan main stem). **Turkey Creek excluded** (CO, no NMRipMap; CO-RIP
   over-predicts, confidence 0.55).
3. **Extent = calibration control, not deliverable** (RF pixel-level F1 0.90–0.92 already solves it).
4. **Score against the right RF baseline:** pixel-level 0.90–0.92 for extent, NOT patch-level 0.701.
5. **Spatial folds** via `assign_spatial_folds` (0.02° blocks → GroupKFold); never random splits.
6. **Fine-tune, don't freeze** — benchmark 5 shows the value is in adapting the encoder.

## 5. Caveats that MUST travel with every number (do not bury)
- **Sensor subset:** all results use **S2 + NDVI only**; S1 SAR / ERA5 / SRTM channels were **masked**
  (not in local cubes). Presto was designed for the full stack → these are a **floor**. Adding S1 SAR
  is the highest-value data improvement and matters for the real product (cloud penetration).
- **Light CPU fine-tune:** 15 epochs, fixed LR 3e-4, 3–5 seeds. A proper GPU recipe (FreezeUnfreeze @
  epoch 20, 10× LR, per the `mangrove` recipe) should do better — so again a floor.
- **Noise floor:** benchmark-6 used 3 seeds; the +0.015 and −0.006 cells are within noise. **Only the
  +0.036 to +0.076 hard-source transfers are load-bearing.**
- **Geographic coverage:** all three tiles are **NM lowland/mid-valley**. The high-elevation headwater
  regime (the original CO-RIP concern) is **untested for transfer**. Basin-scale claims to the CO
  headwaters are unsupported by this evidence.
- **Temporal transfer is unmeasured:** only 2020 has labels, so only *spatial* transfer is scorable.
  The annual-product claim rests on spatial transfer generalizing to time — an inference, not a result.
- **Frozen-Nano retraction context:** the old "OE F1 0.065" was scored against ~45%-wrong labels and
  is retracted; do not cite it. These results use correct labels/folds/year.

## 6. The concrete bar for OlmoEarth-Base
On the **hard-source species transfers** (RF ~0.67 — e.g. Animas→Malpais, Animas→Bloomfield), at
~100–400 labeled px/class, fine-tuned OlmoEarth-Base must:
1. **Beat fine-tuned Presto's ~0.75 ROC** by a margin that justifies 250× the parameters + GPU — not
   merely beat RF (a $0 CPU model already beats RF there).
2. Show the edge **grow, or at least hold, with the full sensor stack** (S1+ERA5+SRTM added).
3. Ideally demonstrate the effect on a **held-out reach** neither trained nor tuned on.

If OlmoEarth-Base cannot clear fine-tuned Presto, the honest conclusion is that the GPU buys nothing a
free CPU model didn't — a valid and valuable result to report.

## 7. Recommended GPU-run plan (for the repo agent)
1. Materialize the 2020 rslearn cube for all three NM tiles (extent + species label layers already
   built here as `*_px.npz`; the branch's `label_layer.py` supersedes for the repo version).
2. Fine-tune OLMOEARTH_V1_1_BASE per `mangrove` recipe; **add S1 SAR** to close the sensor caveat.
3. Reproduce benchmark 6 (three-tile directed transfer) with OlmoEarth in place of Presto; same folds,
   same budgets, ≥5 seeds for a real noise floor.
4. Compare to the bar in §6. Cost per ADR: control AOI ~$2–5, realistic total $30–60, ~2–5 GPU-hr.
5. Requires a GPU compute provider (none configured yet; RunPod L4 ~$0.43/hr or A10G ~$0.34/hr per ADR).

## 8. Literature backbone (methods corpus — reusable)
Full landscape review and a curated 19-source reference table are in the companion methods review;
the searchable corpus is **`riparian_methods_corpus.csv` (320 papers, method-relevance ranked)**.
Load-bearing prior art for this decision:
- **Tseng et al. 2023, Presto** (arXiv 2304.14065) — the model benchmarked here; lightweight
  pixel-timeseries FM, CPU-feasible.
- **Tong et al. 2025, CropGlobe** (arXiv 2509.03497) — simple spectral-temporal features match FM
  embeddings on cross-geography transfer; **the direct challenge our in-tile ties reproduce**, and the
  reason fine-tuning (not frozen embeddings) is the operative variable.
- **Meng et al. 2012** (doi 10.2747/1548-1603.49.4.510) — tamarisk-beetle defoliation mapping on the
  San Juan; AOI-specific, motivates the defoliation confound.
- **Jarchow et al. 2020** (doi 10.1002/hyp.13772) — vegetation-groundwater-ET at Shiprock NM, inside
  the lowland tile.
- Full table + adopt/expand recommendations: `2026-07-16-riparian-fm-methods-review.md`.

## 9. Companion artifacts (all this session, additive, not committed)
Result notes: extent, species, cross-tile transfer, label-budget sweep, fine-tune transfer, three-tile
transfer (this memo consolidates all six). Figures: fig4–fig9. Methods: review + corpus CSV +
reach-generalization note. Reproducibility scripts: `bench_*.py`, `build_*.py`, `lab_*.py`. Presto
install: `PRESTO_SETUP.md` + `presto_working_install.tar.gz`. Data checkpoints: `*_raw_bandcube.npz`,
`*_px.npz` for all three tiles.
