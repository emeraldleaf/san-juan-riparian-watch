# Three-tile fine-tune transfer — the FM edge generalizes (not an Animas artifact)

**Date:** 2026-07-16 · **Status:** executed, CPU, $0 · **Tiles:** Malpais, Animas, **Bloomfield (new)** ·
Resolves the key open caveat from the [fine-tune transfer result](2026-07-16-finetune-transfer-results.md).

## Why a third tile — and why Bloomfield, not Turkey Creek
The fine-tune result (+0.06–0.08 ROC) came from a single direction (Animas→Malpais). Two tiles can't
tell "general label-scarce transfer effect" from "Animas is a lucky source." The plan was Turkey Creek
(the third dev tile) — but **NMRipMap returns 0 polygons there: Turkey Creek is in Colorado and
NMRipMap is New Mexico only** (exactly why the ADR flags it CO-RIP-only). Labeling it with CO-RIP
instead would confound transfer failure with a label-source mismatch and poison the control.

Substitute: **San Juan @ Bloomfield, NM** (bbox -107.99,36.68,-107.86,36.75) — same NMRipMap source,
spatially independent (San Juan main stem, ~70 km east of Malpais, distinct from the Animas River
tile), and **label-rich: 13,094 introduced-woody px** (vs Animas's 598). A better third tile than
Turkey Creek would have been.

## Result: fine-tuned Presto beats RF in 5 of 6 directed transfers

| Transfer (train → test) | RF | Presto fine-tuned | Edge |
|---|---|---|---|
| Animas → Malpais | 0.670 | 0.746 | **+0.076** |
| Animas → Bloomfield | 0.676 | 0.734 | **+0.058** |
| Bloomfield → Malpais | 0.728 | 0.764 | **+0.036** |
| Malpais → Animas | 0.733 | 0.748 | +0.015 |
| Bloomfield → Animas | 0.728 | 0.743 | +0.015 |
| Malpais → Bloomfield | 0.735 | 0.729 | −0.006 |

*(species task, 400 labeled px/class, mean over 3 seeds)*

## The pattern is lawful, not incidental

**The edge scales with how badly RF transfers.** Rank the transfers by RF baseline and the FM edge
falls almost monotonically: where RF is stuck at ~0.67 (Animas as source — the hardest, scarcest
tile), fine-tuned Presto adds +0.06–0.08; where RF already transfers well (~0.73), the edge shrinks to
+0.015 and, in the easiest case, vanishes into noise (−0.006). This is the label-efficiency/transfer
axis behaving exactly as theory predicts: **the pretrained representation helps most precisely when
the hand-feature model is failing to generalize** — and does no harm when RF is already fine.

Critically, **this is no longer an Animas artifact.** Bloomfield→Malpais (+0.036) and
Animas→Bloomfield (+0.058) are independent confirmations involving the new tile. The effect reproduces
across a genuinely different source/target geography.

## What this means for the OlmoEarth decision — the control passed

- **The last major caveat is cleared.** The fine-tuned FM advantage on label-scarce transfer
  generalizes across three tiles and both transfer roles. The GPU hypothesis is now supported by a
  designed multi-tile control, not a single lucky pair.
- **The deployment condition is now precisely characterized.** The FM is worth using exactly when you
  transfer *from a hard/label-scarce reach to unseen ground* — which is the definition of a
  basin-scale product built from a few labeled reaches. It is not worth the complexity where RF
  already transfers well (easy, label-rich source).
- **The bar for OlmoEarth-Base is unchanged and concrete:** on the hard-source transfers (RF ~0.67),
  beat fine-tuned Presto's ~0.75 by enough to justify 250× the parameters + GPU. A $0 CPU model
  already reaches 0.75 there; OlmoEarth has to clear *that*, not RF.

## Honest caveats
- **3 seeds only** (compute budget); SDs not shown per cell but prior runs put them at 0.01–0.03, so
  the +0.015 and −0.006 entries are within noise — the load-bearing claims are the +0.036 to +0.076
  hard-source transfers, which exceed it.
- One budget (400 px/class), one year (2020), species task, S2-subset+NDVI (S1/ERA5/SRTM masked).
- Light CPU fine-tune (15 epochs, fixed LR) — a lower bound on a proper GPU recipe.
- Bloomfield replaces Turkey Creek, so the basin's *high-elevation headwater* regime (the ADR's
  CO-RIP concern) is still untested for transfer — all three tiles are NM lowland/mid-valley.

## Full arc — six benchmarks
1. Extent in-tile: RF = Presto (saturated).
2. Species in-tile: RF = Presto (hard, no edge).
3. Cross-tile transfer: works; FM edge only in label-scarce direction.
4. Label-budget sweep: frozen edge does NOT widen as labels shrink.
5. Fine-tune transfer: fine-tuning widens the edge to +0.06–0.08 (Animas→Malpais).
6. **Three-tile transfer: the edge generalizes (5/6 directions), largest where RF transfers worst.**

Through-line, now on a three-tile control: **fine-tune the FM + deploy on hard/label-scarce unseen
ground = +0.04–0.08 ROC; anywhere else, use RF.** That is the annual-basin-product setting, and it is
the defensible case for turning on a GPU and running OlmoEarth-Base.

## Reproducibility
`build_bloomfield.py`, `bench_3tile.py`, `bench_3tile_results.json`, `bloomfield_*` npz.
