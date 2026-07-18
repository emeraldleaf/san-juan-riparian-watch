# Prior-art audit — CropGlobe (Tong & Wang 2025), "Invariant Features for Global Crop Type Classification"

**Date:** 2026-07-17 · **Method:** `/paper-audit` (WebFetch of the arXiv page) · **Verdict:** 🟡 **GAP**
(a method risk to cite + a sharpened go/no-go bar) — **not a product THREAT**, but the closest thing
to one the FM *premise* has faced. Flagged by the CPU pre-flight memo as "the direct challenge our
in-tile ties reproduce"; this audit says exactly how much of that challenge lands.

## The paper

> **Tong, X.-Y., & Wang, S. (2025).** *Invariant Features for Global Crop Type Classification.*
> arXiv:2509.03497 [cs.LG] (v3, Apr 2026). [abstract](https://arxiv.org/abs/2509.03497)

| | |
|---|---|
| **Task** | Crop type classification under **geographic domain shift** (cross-country → cross-hemisphere) |
| **Data** | CropGlobe: 300k samples, 8 countries, 5 continents; multispectral time series (Sentinel-2-class) |
| **Finding** | *"simple spectral-temporal representations outperform both handcrafted features and modern geospatial **foundation model embeddings**"* — its CropNet *"consistently outperforms larger transformer-based and foundation-model approaches under geographic domain shift"* |
| **Riparian / invasives / native-vs-invasive / change-over-time?** | **None.** Crop type only. |
| **Frozen or fine-tuned FM?** | Compares against FM **embeddings** — i.e. the **frozen-feature** use of a foundation model, not a fine-tuned backbone |

## Why it is NOT a product THREAT

Our novelty claim is a **product** claim: *annual, 10 m, beetle-aware, wall-to-wall,
native-vs-invasive riparian cover + change*. CropGlobe is **crop type classification**. Different
target, different landscape (field polygons vs 50–200 m riparian corridors), no species, no invasives,
no change axis. It cannot "do what we claim nobody has done" because it does not touch the domain. So
it does not scoop the product, and it falsifies no published claim (not RETRACTS).

## Why it is still the strongest challenge the FM *premise* has faced

The memo is right that this is the paper behind our own in-tile ties. Our CPU pre-flight found FM
**ties** RF on extent and in-tile (decision memo §2); CropGlobe is the same phenomenon at global
scale, stated as a headline: *on transfer, simple spectral-temporal features beat FM embeddings.* If
that generalises to riparian, the case for a foundation model weakens — which is exactly the risk this
project exists to test rather than assume.

**But two specifics defang it from "the approach is dead" to "the bar is real":**

1. **It tests frozen FM *embeddings*, not a fine-tuned backbone.** Our own pre-flight already found
   frozen embeddings lose and that **fine-tuning is the operative variable** (memo §5, benchmark 5:
   fine-tuned Presto beats RF on hard-source transfer where frozen did not). CropGlobe reinforces
   "frozen FM features are not magic" — which is *why we fine-tune*, not an argument against our plan.
   It does **not** report a fine-tuned-FM-vs-simple-features comparison on transfer.
2. **Crop type ≠ riparian native-vs-invasive.** CropGlobe's "invariant features" win on a task whose
   classes are separable by spectral-temporal phenology across geographies. Our hard task —
   tamarisk vs Russian-olive vs native, and defoliated-vs-live — is *not* known to be so cleanly
   phenology-separable, which is the whole reason a representation-learning model is worth trying.

## What this does to our positioning (the GAP)

- **Cite it as the standing challenge**, not as settled against us: "the strongest published evidence
  that simple spectral-temporal features can match/beat FM *embeddings* on cross-geography transfer —
  which is why our bet rides on *fine-tuning*, the variable CropGlobe does not test."
- **It sharpens the go/no-go bar rather than moving it.** The memo already says: beat fine-tuned
  Presto's ~0.75, not merely RF. CropGlobe raises the stakes on that bar — if fine-tuned
  OlmoEarth-Base *cannot* clear a strong simple/lightweight baseline on transfer, CropGlobe's thesis
  wins by extension, and the honest report is "the GPU bought nothing." That is already the Phase-1
  abort criterion; CropGlobe is one more reason to hold it.
- **A CropNet-style simple baseline belongs in the Phase-1 comparison.** We benchmark against RF and
  fine-tuned Presto; adding a spectral-temporal "invariant features" baseline (cheap) makes the
  transfer comparison honest against the current SOTA-of-simplicity.

## What remains ours after conceding the point

Everything the product claim rests on. CropGlobe concedes nothing about riparian, invasives, the
beetle, the time axis, or 10 m native-vs-invasive mapping. It bounds a *method assumption* (frozen FM
embeddings) we had already discarded, and it names the baseline we must beat by fine-tuning. The
contribution — *can a fine-tuned EO FM turn abundant weak riparian labels into better scarce-label
transfer for extent and invasives* — is untouched, and now has a clearer, harder bar.

## What changed in the repo

- This audit added to the [falsification log](README.md); CropGlobe removed from "Still to audit".
- Draft issue (a Phase-1 baseline): **add a CropNet-style spectral-temporal "invariant features"
  baseline** to the transfer benchmark alongside RF and fine-tuned Presto, so the go/no-go bar is
  measured against the strongest *simple* method, not only RF.
