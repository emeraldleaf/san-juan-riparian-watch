# Methods & metrics — how we measure it, and why the measurement is honest

This is the companion to the results: what the two models actually *are*, what every number
(**AUC, F1, precision, recall, accuracy**) actually *means*, what "overfitting" is and what we are
fitting, and — the part that separates a credible result from a plausible one — **why our evaluation
protocol makes the comparison fair.**

**There are two classification tasks, and they share all the same machinery** (the same RF and FM
models, the same 144-D features, the same metrics):

1. **Extent / delineation — "riparian vs other."** Per pixel: is this **riparian vegetation** or the
   surrounding corridor (water / agriculture / other)? This is the calibration control — extent is a
   solved problem, so it tests whether the pipeline works at all.
2. **Invasives — "invasive vs native."** Per pixel *inside* the riparian corridor: is it **invasive**
   (tamarisk / Russian-olive) or **native** (cottonwood / willow)? This is the actual product.

Both models see the same evidence and are scored the same way; only the label changes. Where a running
example helps, invasives (task 2) is used — it is the harder and more interesting of the two.

*(Canonical pointer to this doc is in CLAUDE.md → Reach-cube materialization. See CLAUDE.md.)*

---

## 1. The task, precisely

For every pixel inside the mapped riparian corridor we predict one label: **invasive** or **native**.
The evidence each model sees is a **spectral-temporal feature vector** — **12 Sentinel-2 bands × 12
monthly mosaics = 144 numbers per pixel** — the seasonal trajectory of reflectance. The
discriminating signal is *phenological*: tamarisk and Russian-olive leaf out and senesce on a
different schedule than cottonwood/willow, with a distinct **short-wave-infrared** water signature.
(We showed empirically that **NDVI alone is ~random for this** — AUC ≈ 0.5; the signal lives in
SWIR/red-edge, which is why the models get the full 144-D vector, not a vegetation index.)

---

## 2. The two models

### Random Forest (RF) — the baseline
An **ensemble of ~300 decision trees**. Each tree is trained on a **bootstrap sample** of the pixels
(sampling with replacement) and, at each split, considers a **random subset of the 144 features**.
Each tree votes; the forest averages the votes into a probability. Two properties matter:
- **It is per-pixel and context-free** — it sees one pixel's 144 numbers, with no spatial neighbours.
- **Bagging + feature randomness reduce variance** — the averaging is what makes RF resist
  overfitting on small data. It is a genuinely strong, cheap baseline (no GPU).
- `class_weight="balanced"` re-weights the loss so the minority class isn't ignored.

### Foundation model (FM) — OlmoEarth, fine-tuned
A **pretrained vision transformer** (≈207 M parameters) trained by Ai2 on huge amounts of unlabelled
satellite imagery, then **fine-tuned** on our labels. Unlike RF it sees a **32×32-pixel window with
spatial context** (self-attention across pixels and months) and predicts a **per-pixel** map through a
`UNetDecoder`. Two terms that recur:
- **Frozen embeddings vs fine-tuning.** "Frozen" = use the pretrained network as a fixed feature
  extractor and train only a small head on top. "Fine-tuning" = unfreeze the network and update its
  weights on our task. We use `FreezeUnfreeze`: train the head first, then unfreeze the encoder at
  epoch 20 at a lower learning rate. **Fine-tuning is the load-bearing variable** — frozen embeddings
  lose to RF; whether *fine-tuning* wins is the whole question.
- **Why it might help — and might not.** The pretraining could encode transferable structure that a
  from-scratch RF lacks. But 207 M parameters need a lot of labels; on a few hundred windows it can
  simply **memorise** (see §4).

---

## 3. The metrics — what each number means

Every metric derives from the **confusion matrix**: for the "invasive" class, each pixel is a
**TP** (predicted invasive, is invasive), **FP** (predicted invasive, is native), **FN** (predicted
native, is invasive), or **TN**.

| Metric | Formula | Plain meaning | What it's blind to |
|---|---|---|---|
| **Precision** | TP / (TP + FP) | *When the model says "invasive," how often is it right?* | Missed invasives (FN) |
| **Recall** (sensitivity) | TP / (TP + FN) | *Of the invasive that's really there, how much did it catch?* | False alarms (FP) |
| **F1** | 2·P·R / (P + R) | Harmonic mean of precision & recall — one number balancing the two | Depends on the **threshold** and on **prevalence** |
| **Accuracy** | (TP + TN) / all | Fraction of pixels correct | **Class imbalance** — see below |
| **ROC-AUC** | area under TPR-vs-FPR curve | Probability a random invasive pixel is scored **higher** than a random native one | The chosen threshold; prevalence |

Three things worth internalising:

- **Accuracy lies under imbalance.** Malpais is 82% invasive. A model that predicts "invasive
  everywhere" scores **82% accuracy** while being useless. That is why we do **not** headline
  accuracy for the invasive task.
- **F1 is an *operating-point* metric.** It's computed at one decision threshold (we use argmax ≈
  0.5). It answers "how good is the model *as you'd deploy it*." But it moves when prevalence moves —
  a fixed threshold that's well-tuned on a 47%-invasive reach is mis-tuned on an 82%-invasive one, so
  F1 can drop even if the model's *ranking* is unchanged.
- **AUC is a *ranking* metric, and it is prevalence-invariant.** It asks only "does the model score
  invasive pixels above native ones," across *all* thresholds. **0.5 = random, 1.0 = perfect,
  < 0.5 = anti-correlated** (a real signal, pointing the wrong way — which is exactly how we caught
  the mis-composited fetch at AUC 0.37). Because it doesn't depend on threshold or base rate, **AUC
  is the fair metric for a transfer test across a prevalence gap.**

**We report AUC *and* F1 on purpose.** AUC tells you whether the model *can* separate the classes; F1
tells you what you'd get *at a usable threshold*. When they diverge under a prevalence shift, that
divergence is information, not noise.

---

## 4. What we're fitting, and what "overfitting" is

**Fitting** = choosing the model's internal parameters so it maps features → label well on the
**training** data. RF fits its trees' split thresholds; the FM fits its 207 M weights by gradient
descent.

**Overfitting** = the model fits the *idiosyncrasies and noise* of the training pixels rather than the
*generalisable* signal. The signature is unmistakable: **training error keeps falling while validation
error rises.** We watched the FM do exactly this — its training class-loss collapsed toward **0.01**
while validation loss climbed back from **0.50 → 0.95**. It had memorised a few hundred training
windows. RF resists this because **bagging averages many high-variance trees into a low-variance
ensemble**, and because a per-pixel tree can't memorise *window* identity the way a 207 M-parameter
attention network can.

**What signal we want it to fit:** the SWIR/red-edge **phenological trajectory** that separates the
species — not NDVI (near-random here), not the label's spatial layout, and not the specific reach.

We **guard against overfitting** three ways: a held-out **validation** split to pick the best
checkpoint (never the test set); **early stopping** when validation stops improving; and — the real
test — **transfer to a different reach** the model never saw.

---

## 5. The evaluation protocol — why the comparison is fair

A number is only as trustworthy as the split that produced it. Three disciplines:

1. **Spatial, not random, splits.** Neighbouring 10 m pixels are near-duplicates (strong spatial
   autocorrelation). A random train/test split leaks near-copies across the boundary and inflates
   every metric. So we split by **space** — the RF baseline uses `GroupKFold` on spatial blocks; the
   FM uses whole spatially-separated window groups; and the strongest test trains on one reach and
   tests on a **geographically distinct** one.
2. **Prevalence shift is named, not hidden.** Farmington is 47% invasive, Malpais 82%. We report AUC
   (prevalence-invariant) as the primary transfer metric precisely because F1 at a fixed threshold
   would be dragged around by that shift.
3. **Head-to-head, same footing.** This is the correction we made against ourselves: the published RF
   "0.90–0.92" was a *binary, threshold-tuned, cross-validated* number, not comparable to the FM's
   *5-class, argmax, single-split* number. The honest comparison re-runs **both models on the same
   pixels, the same features, and the same scoring**. Only same-footing numbers get compared.

**In-domain vs transfer.** An in-domain score (train and test in the same reach) measures *fit*; a
**transfer** score (train Farmington, test Malpais) measures *generalisation* — what a deployed model
actually faces. In-domain always flatters. The transfer number is the one that decides anything.

---

## 6. Reading our numbers

### Task 1 — extent (riparian vs other), head-to-head, identical scoring

| Model (same pixels, same 144-D features, same all-pixel F1) | riparian F1 |
|---|---|
| **RF, class-balanced** | **0.83** |
| FM (fine-tuned, per-pixel decoder) | 0.76–0.77 |
| *published RF "0.90–0.92" — different harness, NOT comparable* | *inflated* |

Two honest caveats, both ours: the published **0.90–0.92 was inflated** (binary, threshold-tuned,
cross-validated — not the same measurement), and the NMRipMap **zone labels are noisy** (they include
ag/bare ground inside the mapped corridor), which caps *everyone's* F1 and means the 0.06 RF-over-FM
gap sits **within the label-noise envelope**. Net: on extent, RF is at least as good as the FM, for
free — but extent was only ever the control.

### Task 2 — invasives (invasive vs native)

| Setting | What it measures | RF |
|---|---|---|
| in-domain, 5-fold spatial CV | fit + modest generalisation | AUC 0.85 |
| **transfer, Farmington → Malpais** (aligned) | true cross-reach generalisation | **AUC 0.80 / F1 0.68** |
| transfer on a **mis-composited** cube | *nothing* — a broken control | AUC 0.37 (artifact) |

The RF drops only 0.05 AUC from in-domain to a real cross-reach transfer across a 47%→82% prevalence
gap — it **generalises well**. The FM must beat that 0.80 on the same test to justify its cost; on
every cheaper test so far it has not, and its failure mode has been **overfitting** the small training
set — which is exactly the quantity a foundation model's pretraining is *supposed* to rescue, and the
reason the transfer test is the one that matters.

> **The one-sentence version:** we score with **AUC** (threshold-free, prevalence-invariant ranking)
> and **F1** (deployed operating point) on **spatially-held-out** data, compare models **on identical
> footing**, and treat **cross-reach transfer** — not in-domain fit — as the verdict, because that is
> the only setting where overfitting has nowhere to hide.
