# Phase 3 — the deep-time, cross-sensor, beetle-aware change product

**This is the contribution.** Everything before it — extent, invasives, RF vs FM at a single epoch —
was calibration. The product is an **annual riparian extent + native-vs-invasive cover time series**
across the full satellite record, **back past Sentinel-2 (2015) into the Landsat era (1984→)** — far
enough to see the **pre-beetle baseline**. Nobody has this for the basin. See CLAUDE.md.

> **The one-line thesis:** a reach is not healthier because it is greener; total cover can rise while
> the corridor degrades, because the rise is *Tamarix* replacing cottonwood and willow — and the only
> way to prove that is to watch it happen, annually, for forty years.

---

## Why this reopens the RF-vs-FM decision

At a single epoch (2020, Sentinel-2) RF and the fine-tuned foundation model **tie** — same ranking
(AUC 0.80 on cross-reach transfer), RF cheaper. That settles the *single-map* choice: ship RF.

**But the deep-time product is a different problem — transfer across *sensors* and *decades*, not one
epoch — and that is the one regime where the FM has a *structural*, not hypothetical, advantage:**

- **Pre-2015 is Landsat-only.** OlmoEarth is pretrained on Landsat *and* Sentinel-2; it can ingest both
  into one embedding space. RF would need a **separate model per sensor** and manual cross-calibration
  at every seam. For a *consistent* 1984→2026 series, that difference is real.
- **The robustness that produced the transfer tie** is exactly what a 40-year, multi-sensor series
  demands (every year a different atmosphere, every sensor a different radiometry).

So the decision is genuinely reopened — and this spec's first job is to **measure** it, not assume it.

---

## Three hard truths — mostly *not* about RF vs FM

1. **No labels before ~2017.** NMRipMap is 2020, CO-RIP 2018, CSU points 2017. Every earlier year is
   **backward extrapolation** from recent labels. This is the fundamental risk; both models face it.
2. **The beetle inverts the signal mid-record.** *Diorhabda* hit the San Juan **2004–2007**, saturated
   the Upper Basin by 2014. Pre-beetle, tamarisk *held green late* (the classic discriminator);
   post-beetle, defoliated tamarisk *browns early* — the signal flips. Our labels are **all
   post-beetle**, so predicting 1990 tamarisk means recognising a signature the model never saw, for a
   class whose appearance *changed*. **Identifiability, not model capacity** — no model choice fixes it.
3. **Landsat 30 m can't resolve the corridor.** CO-RIP said it in their own words: without a finer
   sensor the tamarisk phenological signature is *"a difficult constraint to overcome."* The corridor
   is ~3 px at 30 m and blurs into agriculture. **Physics caps pre-2015 accuracy regardless of RF/FM.**

The model is the *smaller* risk. Plan accordingly.

---

## The plan — cheapest-decisive-first (the method that's worked all along)

### Phase 3A — the cross-sensor test (make-or-break, $0 laptop)
Can a model trained on Sentinel-2 hold on Landsat? Test where ground truth exists: build **S2 2020 and
Landsat 2020** cubes on **one enforced common footprint** — the same AOI, reprojected to a single
10 m EPSG grid, restricted to the **6 shared bands** (blue/green/red/NIR/SWIR-1/SWIR-2), each converted
from its own DN scaling to **surface reflectance (0–1)** so the values are comparable. (Landsat's true
30 m resolution is the effective floor — resampling to 10 m aligns the grids without inventing detail.)
Train RF on the S2 side, predict the **same held-out pixels' Landsat** side. The **AUC drop is the
sensor penalty** — it isolates band + radiometry + resolution, because pixels and labels are identical.

> ### 🚦 GATE. If RF's cross-sensor AUC holds (≈ in-domain), RF may suffice for the archive — no GPU.
> If it fragments, that is the first *measured* justification for the FM, and we run the FM
> cross-sensor test on a rented GPU. **Decide the architecture on this number, not on the single-epoch
> tie.**

### Phase 3B — the temporal test ($-cheap)
Train on 2020, predict **2017** (Landsat), score against the CSU 2017 points — the only other-year
labels that exist. Holds across a sensor swap *and* three years → the archive is plausible.

### Phase 3C — the beetle strategy (decide the scope now)
No pre-2017 labels will ever exist. Split the product by what is defensible:
- **Extent (riparian vs not) — the full record, 1984→.** More stable across the beetle; the honest
  deep-time layer.
- **Species (native vs invasive) — post-beetle, where labels exist**, plus a **research push**: add a
  **defoliated-tamarisk class** from the 283 CSU defoliation points so the model knows tamarisk in
  *both* live and defoliated states — the one shot at extending species backward, and the FM's
  label-scarce home turf.

### Phase 3D — plausibility checks, *not* validation (no ground truth)
You cannot **validate** 1990 predictions — there are no 1990 labels to validate against. What you can
do is **corroborate**: check that the output is *consistent with independent evidence*. Tamarisk stress
should appear in the right places at the right time (beetle release 2004–07, saturation by 2014);
trajectories should agree with **CO-RIP** and **Perkins et al. (Canyonlands, 1940–2022)**. Call this
what it is — **plausibility / corroboration**, not validation. It raises or lowers confidence; it never
proves correctness, and the writeup must say so.

### Phase 3E — produce the archive (mostly CPU)
Roll the calibrated model across the Landsat + S2 archive: annual extent (full record) + annual
native-vs-invasive (post-beetle, caveated earlier). Inference is embarrassingly parallel and needs no
training GPU — on-demand batch, zero idle cost (hosting ADR).

---

## Risk register — the honest version

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Cross-sensor gap too large** (RF and FM both fragment Landsat↔S2) | Medium | 3A measures it first, for free. If both fail, the deep record is *extent-only*. |
| **Beetle inversion breaks the species series pre-2004** | **High — and interesting** | Pre-registered: extent deep, species post-beetle; defoliation class as the research reach. A *finding*, not a failure. |
| 30 m can't resolve the corridor | **High, physical** | Report extent at a coarser MMU pre-2015; do not over-claim species at 30 m. |
| No historical ground truth | Certain | Validation-by-consistency against the beetle timeline + published change maps. |
| FM cross-sensor edge is *also* only a tie | Medium | Then RF + per-sensor harmonization is the pragmatic archive — cheaper, and 3A/3B will have said so. |

## What we are NOT doing
- **No committing the archive architecture before 3A/3B.** The cross-sensor number decides RF vs FM.
- **No un-caveated species product pre-beetle.** The inversion + label gap forbid it.
- **No always-on GPU** — inference is batch (hosting ADR); the GPU appears only if 3A says the FM earns it.
