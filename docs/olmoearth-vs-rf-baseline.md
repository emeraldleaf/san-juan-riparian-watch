# RF baseline vs. OlmoEarth foundation model — riparian delineation

**Updated 2026-07-12.** The head-to-head that the Stage-1 pipeline was built around
([spec](specs/2026-07-03-stage1-riparian-delineation.md), the *two-implementations*
test): a hand-engineered RandomForest vs. Ai2's **OlmoEarth** Earth-observation
foundation model.

> ## ⚠️ The 2026-07-06 result on this page is RETRACTED
>
> It reported **RF F1 0.73 vs OlmoEarth F1 0.46** and concluded the baseline won. That
> comparison was **not valid**, for three independent reasons found afterwards:
>
> 1. **The ground truth was ~45 % wrong.** `fetch_nmripmap` rasterized *every* NMRipMap
>    polygon as riparian. On this AOI, 341 polygons are mapped but only **189 are woody
>    riparian** — the rest are developed, agriculture, upland and water, all of which were
>    being taught to both models as riparian. Both numbers were scored against corrupted
>    truth ([#11](https://github.com/emeraldleaf/san-juan-riparian-watch/issues/11), fixed).
> 2. **The foundation model's time axis was averaged away.** `extract_embeddings`
>    mean-pooled encoder tokens over time, deleting the phenology signal that riparian
>    detection depends on ([#9](https://github.com/emeraldleaf/san-juan-riparian-watch/issues/9)).
> 3. **The AOI was never recorded**, so the run could not be reproduced at all.
>
> The re-run below fixes all three. **Its headline finding contradicts the hypothesis in
> #9**, and is reported anyway.

## The fair test

Everything is held constant except the **representation**: same AOI, same corrected
labels, same patch grid, same spatial folds, same RandomForest head.

| | |
|---|---|
| AOI | `(-108.80, 36.86, -108.75, 36.90)` — Malpais tile (HUC12 `140801051001`), San Juan River, NM. **Recorded this time.** |
| Imagery | Sentinel-2 L2A, `2024-04-01/2024-11-01` (green-up → senescence), ≤30 % cloud |
| Cube | 384×384 px @ 10 m, **12 timesteps** (monthly — matching Ai2's own `mangrove` recipe) |
| Truth | NMRipMap **woody riparian only** (the corrected crosswalk) |
| Grid | 2 304 patches of 8×8 px (80 m); **15 % riparian** |
| Validation | 4-fold spatial CV, whole ~400 m blocks held out (90 blocks) |
| Head | the *same* `_cv_estimator()` RandomForest for every arm |

## Result

| Arm | dim | Precision | Recall | **F1** | ROC-AUC |
|---|---|---|---|---|---|
| **RF — 22 hand features** (patch-mean) | 22 | 0.71 | 0.71 | **0.701** | **0.951** |
| OlmoEarth v1.1-Nano — `mean_time` *(the retracted harness)* | 128 | 0.48 | 0.01 | 0.021 | 0.609 |
| OlmoEarth v1.1-Nano — `temporal_stats` | 512 | 0.78 | 0.04 | 0.065 | 0.634 |
| OlmoEarth v1.1-Nano — `concat_time` | 1536 | 0.38 | 0.03 | 0.059 | 0.630 |

Checkpoint control (same AOI, same folds):

| Checkpoint | `mean_time` F1 / AUC | `temporal_stats` F1 / AUC |
|---|---|---|
| OlmoEarth-v1-Nano | 0.017 / 0.618 | 0.048 / 0.648 |
| OlmoEarth-v1.1-Nano | 0.021 / 0.609 | 0.065 / 0.634 |

> ### ⚠️ Known defect in this run: the labels and the imagery are 4 years apart
>
> Found after publishing. NMRipMap's service metadata says **v2.0 Plus (Muldavin et al. 2023)** was
> photo-interpreted from **NAIP 2020** — so the labels are **2020-vintage**. This run used
> **Sentinel-2 from 2024**.
>
> Riparian corridors move over four years (beetle defoliation, floods, channel migration,
> restoration), so we fed every arm label noise we introduced ourselves.
>
> - The **relative** comparison **still stands** — RF and OlmoEarth ate the *same* mismatch.
> - The **absolute** numbers are **pessimistic for every arm**. RF's 0.701 and OlmoEarth's 0.065
>   are both depressed.
> - It would hurt an **invasives** task far more than this extent task: riparian extent is fairly
>   stable over four years, but *Tamarix cover* is precisely what has been changing since the
>   beetle arrived.
>
> **The fix, for any future run: fit on imagery contemporaneous with the label vintage** — i.e.
> Sentinel-2 **2020**. See
> [the fine-tune ADR](decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md).

## What this actually shows

**1. The pooling bug is real — and it is *not* the explanation.**
Issue #9 argued that mean-pooling over time was "the killer", and that un-crippling it
would flip the result. Fixing the pooling helps **consistently but marginally**: F1 roughly
triples (0.021 → 0.065) and AUC gains ~0.03, on *both* checkpoints. It comes nowhere near
RF's 0.701 / 0.951. **The hypothesis this issue was opened on is not supported.**

That the defect is real is not in doubt — it is pinned by a unit test
(`tests/test_olmoearth_pooling.py::test_mean_time_destroys_phenology`) that builds two
classes with **identical seasonal means and different trajectories** (the riparian-vs-
irrigated-crop confusion, exactly). Under `mean_time` they collapse to the same vector and
no classifier can separate them; under `temporal_stats` they separate perfectly. But a
defect being real does not make it the *cause* of the gap, and here it isn't.

**2. Under corrected labels, the frozen-embedding setup is much worse than it looked.**
The retracted OlmoEarth F1 was 0.46; the corrected-label F1 is 0.065. The old labels
rewarded predicting *corridor membership* (urban, agriculture, water and upland inside the
valley were all "riparian"), and a frozen foundation-model embedding is good at exactly
that — landform and context. Score it on the real task — *woody riparian vegetation, not
the valley it sits in* — and that apparent skill largely evaporates. **The corrupted labels
were flattering the foundation model, not handicapping it.**

**3. Recall, not ranking, is what collapses.** AUC ~0.63 means the embeddings carry real
signal; precision is respectable (0.78). Recall is 0.04. The head can rank but cannot find
riparian patches at threshold — consistent with 80 m patches being coarse relative to a
narrow corridor, and with a 128-dim frozen embedding trained for no particular task.

**4. v1.1 is the right default.** It matches v1 in quality (slightly better F1, slightly
lower AUC — within noise) while merging Sentinel-2 into single tokens: the returned token
tensor has a band-set axis of **1 vs v1's 3**, i.e. **~3× fewer tokens** for the same cube.
Cheaper for free. `DEFAULT_MODEL_ID = OLMOEARTH_V1_1_NANO`.

## What is still untested — and it is the part that matters

None of this tests **OlmoEarth as Ai2 actually recommends using it.** Every arm above is a
*frozen encoder feeding a scikit-learn RandomForest*, which is not a configuration Ai2
endorses anywhere. Their `mangrove` recipe — the near-exact analog of this task, reporting
**97.6 % overall accuracy** — instead:

- fine-tunes **`OLMOEARTH_V1_BASE`** (not the smallest Nano),
- **unfreezes the backbone** (`FreezeUnfreeze`, epoch 20, 10× LR),
- uses a **`SegmentationPoolingDecoder`** consuming patch tokens directly — no pooled
  vector, no RF head.

So the honest statement is narrower than either the old page or #9 claimed:

> On this AOI, a **frozen OlmoEarth-Nano embedding + RF head** is far worse than a
> hand-engineered RF baseline, and temporal pooling explains only a small part of the gap.
> Whether a **fine-tuned OlmoEarth-Base with a segmentation decoder** beats the baseline is
> **still an open question** — it has not been run.

That run needs a GPU and is what [#9](https://github.com/emeraldleaf/san-juan-riparian-watch/issues/9)
now tracks. The scaffold is committed at `olmoearth_run_data/riparian_extent/`.

## A methodological note worth keeping

While debugging this, a sanity probe ("can the embeddings predict their own patch's
NDVI?") returned **AUC 0.23** — far *below* chance, which looks like a catastrophically
broken encoder. It wasn't. `cross_val_score(cv=4)` uses an **unshuffled** KFold, so on a
raveled spatial grid the folds are contiguous spatial bands; with a spatial NDVI gradient
the learned relationship inverts across folds. With `KFold(shuffle=True)` the same
embeddings score **AUC 0.85** — they were fine all along.

The lesson is the same one this whole page is about: **a bad number is a claim about your
harness until you prove otherwise.** The spatial folds used for the real results above are
deliberately unshuffled — that is correct there, because held-out *blocks* are the honest
test of spatial generalization. It is only wrong for a sanity probe.

## Reproduce

```python
from riparian.delineation.runner import run_delineation               # RF
from riparian.delineation.olmoearth import run_delineation_olmoearth  # OlmoEarth

run_delineation_olmoearth(
    bbox=(-108.80, 36.86, -108.75, 36.90),
    engine=engine,
    date_range="2024-04-01/2024-11-01",
    max_timesteps=12,            # the encoder's temporal embedding table holds exactly 12
    pooling="temporal_stats",    # "mean_time" reproduces the retracted result
)
```
