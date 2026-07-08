# RF baseline vs. OlmoEarth foundation model — riparian delineation

**2026-07-06.** The head-to-head that the Stage-1 pipeline was built around
([spec](specs/2026-07-03-stage1-riparian-delineation.md), the *two-implementations*
test): a hand-engineered RandomForest vs. Ai2's **OlmoEarth** Earth-observation
foundation model, on the *same* AOI and the *same* NMRipMap truth.

## The two tracks

| | RandomForest (`run_delineation`) | OlmoEarth (`run_delineation_olmoearth`) |
|--|----------------------------------|------------------------------------------|
| Representation | 22 hand features (NDVI/NDMI/NDRE/kNDVI/EVI + terrain), **per 10 m pixel** | OlmoEarth-v1-**Nano** multimodal embeddings (D=128), **per 8×8 patch (80 m)** |
| Labels | NMRipMap (rasterized truth) | NMRipMap, majority-aggregated to patches |
| Head | RandomForest | RandomForest on the embeddings |
| Validation | 5-fold spatial CV (held-out blocks) | 5-fold spatial CV (held-out blocks) |

Both were run on a **balanced ~2.6 km AOI (≈36 % riparian)** in the Malpais tile
(San Juan River, NM), Sentinel-2 leaf-on 2023, **CPU**, 5 timesteps.

## Result (5-fold spatial CV — the honest, held-out metric)

| Model | Precision | Recall | **F1** | ROC-AUC |
|-------|-----------|--------|--------|---------|
| **RandomForest** | 0.83 | 0.67 | **0.73** | 0.90 |
| **OlmoEarth-Nano** | 0.68 | 0.50 | **0.46** | 0.79 |

**The RF baseline wins this comparison** — and that is the *expected, defensible*
outcome given the setup, not a failure of the foundation model.

## Why RF leads here (the analysis is the point)

1. **Patch resolution (80 m) is the dominant handicap.** OlmoEarth embeds 8×8-pixel
   patches, so it delineates at 80 m. Riparian corridors are narrow, and on a
   *balanced edge* AOI (where the boundary is what matters) RF's per-pixel 10 m
   resolution resolves the edge that OlmoEarth's coarse patches cannot.
2. **~64× fewer training samples for the head.** RF trains on ~65 k pixels; the
   OlmoEarth head on only ~1 k patches. A 128-dim head on 1 k samples is
   data-starved, and spatial CV correctly penalizes it.
3. **Nano + 5 timesteps suppress the FM's strengths.** This is the *smallest*
   OlmoEarth model, temporally subsampled for CPU — exactly the axes (model
   capacity, temporal depth, multimodality, label-efficiency) where a foundation
   model earns its keep.

## Where OlmoEarth is expected to win

The FM's advantages compound at **scale**, which is the "OlmoEarth everywhere" (GPU)
plan: many tiles (so the head sees abundant patches *and* the FM's **label
efficiency** compounds — better accuracy from the same scarce NMRipMap labels), a
**larger model** with finer effective patching, **full temporal depth**, and SAR +
terrain fusion. The CPU/Nano/small-AOI comparison is honest precisely *because* it
shows the baseline is hard to beat until you lean into those strengths.

## What this establishes for the project

- **OlmoEarth-v1-Nano runs end-to-end on CPU.** Resolving the tokenizer's mask
  convention (`(1,H,W,T,band_sets)`) and the square-patch-grid constraint was the
  one piece deferred as "finish on the GPU VM"; it's done (see
  `riparian/delineation/olmoearth.py`).
- A **fair, reproducible RF-vs-FM harness** (same AOI, same truth, same spatial-CV),
  with the honest interpretation of *when* the foundation model pays off.

## Reproduce

```python
from riparian.delineation.runner import run_delineation             # RF
from riparian.delineation.olmoearth import run_delineation_olmoearth  # OlmoEarth
# same bbox, date_range, engine; compare .cv.metrics
```

## Next

Basin-scale OlmoEarth on the GPU VM (larger model, full temporal, persisted
embedding store) to test the label-efficiency thesis; RF-vs-OlmoEarth disagreement
maps as an uncertainty layer.
