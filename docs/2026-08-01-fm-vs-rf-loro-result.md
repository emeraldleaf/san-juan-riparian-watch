# The foundation model earns its keep — but only where the baseline was blind

**Date:** 2026-08-01 · **Status:** result · settles the
[FM-vs-RF deploy decision](specs/2026-07-19-fm-vs-rf-deploy-decision.md) against the measured
[RF bar](2026-07-20-diverse-reach-transfer.md). Metric/method background:
[methods & metrics](2026-07-18-methods-and-metrics.md).

## The one-sentence answer

Fine-tuning a satellite **foundation model** (OlmoEarth) does **not** beat a plain **Random Forest**
everywhere — it *ties* the RF on the river reaches the RF already handled — but it **rescues the one
morphology the RF was blind to** (a desert arroyo: **AUROC 0.557 → 0.889**), and that rescue is enough
to win the deploy decision.

---

## For the newcomer: what is this even about?

**The task.** Draw, from satellite imagery, *where the riparian vegetation is* — the ribbon of green
(cottonwood, willow, and invasive tamarisk) that lines a desert river. That map is the foundation for
everything downstream: monitoring invasive spread, scoring corridor health, tracking change over decades.

**Why it's hard.** A river corridor is thin and its *shape* changes along its length. A **wide
floodplain river** near a town looks nothing like a **narrow arroyo** — a dry, incised desert wash that
only runs after storms. A model that learns "riparian looks like *this*" on wide rivers may have no idea
what to do with an arroyo.

**The two contenders.**

- **Random Forest (RF)** — the workhorse baseline. It looks at each **10 m pixel on its own** — its
  stack of ~72 numbers (12 months × 6 spectral bands) — and asks "is this pixel riparian?" It is
  **context-free**: it never sees a pixel's neighbours. Cheap, fast, and the standard in this field.
- **Foundation model (OlmoEarth)** — a large neural network **pretrained on enormous amounts of
  satellite imagery**, then fine-tuned on our labels. Crucially it reads a **32×32 pixel window with
  self-attention** — it sees a pixel *in the context of its surroundings*, so it can learn "riparian
  *because* it sits in a corridor-shaped patch along a drainage." That spatial context is its one
  structural advantage, and it costs real money (a GPU) to train.

**The question this document answers:** is that spatial context worth the GPU? We had already measured
the RF. This is the foundation model, measured on the *same* honest test.

---

## The honest test: leave-one-reach-out

You cannot judge "does it transfer to unseen ground?" by testing on ground the model trained on. So we
use **leave-one-reach-out (LORO)** over **four morphologically-diverse New Mexico reaches**:

| reach | morphology |
|---|---|
| Farmington | wide river (San Juan/Animas confluence) |
| Kirtland | semi-arid mainstem |
| Aztec/Animas | montane-fed tributary |
| **Malpais** | **narrow desert arroyo** — the one unlike the others |

For each reach in turn: **train on the other three, predict the held-out one.** The held-out reach's
score is the *transfer* number — how well the model does on morphology it never saw. Both models are
measured this way, on **identical 12-month median-mosaic Sentinel-2 cubes** (same pixels, same
compositing), so the comparison is apples-to-apples.

The RF's numbers were measured first (the "bar"). The arroyo is the crux: pooling three river reaches
taught the RF nothing useful about arroyos, and its Malpais transfer collapsed to **AUROC 0.557** —
barely above a coin flip (0.5). *That gap is the foundation model's one predicted opening.*

---

## The result

Held-out **riparian ROC-AUC** per fold — foundation model vs the RF bar:

| held-out reach | morphology | **FM** | RF | Δ (FM − RF) |
|---|---|---|---|---|
| **Malpais** | **arroyo** | **0.889** | 0.557 | **+0.332** |
| Farmington | wide river | 0.892 | 0.905 | −0.013 |
| Kirtland | mainstem | 0.812 | 0.845 | −0.033 |
| Aztec/Animas | tributary | 0.894 | 0.886 | +0.008 |
| **macro-mean** | | **0.872** | 0.798 | **+0.074** |

*(ROC-AUC: 1.0 is perfect, 0.5 is chance. "Macro-mean" = the unweighted average across the four folds,
which deliberately weights the lone arroyo equally with the three river reaches.)*

**The verdict is GO** — the foundation model clears the pre-registered **+0.04 macro-mean** bar (it wins
by **+0.074**). But the number hides the real story, which the per-fold column tells:

> On the **three river-corridor reaches the RF already handled well** (0.845–0.905), the foundation
> model **merely ties** — it even *trails* on Kirtland by 0.03. **Every bit** of its macro-mean advantage
> comes from **one fold: rescuing the arroyo, 0.557 → 0.889.**

The foundation model is **not a uniformly better model.** It is a **specialist for the hard,
under-represented morphology.** Where the training distribution already covers the target (river
reaches), the cheap per-pixel RF is just as good. Where it doesn't (the arroyo), the RF is near-blind and
the foundation model's spatial context is transformative. This is *exactly* what the
[CPU pre-flight](audits/2026-07-16-DECISION-MEMO-olmoearth-gpu.md) predicted a foundation model would buy:
**"hard/label-scarce transfer to unseen ground,"** and nothing more.

---

## For the practitioner: the method, and where to attack it

### The unbiased split (this is the part that most often goes wrong)

A leave-one-reach-out score is only honest if the held-out reach is **never used to choose the model.**
The naive mistake is to early-stop or pick the best epoch on the held-out reach — that is *selecting on
the test set*, and it inflates every number. So each fold uses a **three-way split**:

- **test** = the held-out reach — scored **exactly once**, at the end.
- **train / val** = a spatial hash split *of the three training reaches only*. Epoch selection and
  early-stopping use **val** (from the training distribution), never the held-out reach.

Concretely, holding out Malpais gives **729 train / 347 val / 328 test** windows, with the held-out reach
contributing to *test only*. This mirrors how the RF bar was computed (a single-shot fit, no
epoch-selection), so neither model gets a peeking advantage.

### The model

`OLMOEARTH_V1_BASE` (207 M params) + a **per-pixel `UNetDecoder`** (riparian is inherently per-pixel;
a per-window pooling head cannot be scored against a pixel-level ROC). `FreezeUnfreeze`: the pretrained
encoder is **frozen until epoch 20**, then unfrozen at 10× lower LR. 100 epochs, batch 32, AMP, on a
single **RTX A6000**; ~46 min/fold. Input is **12 monthly median mosaics** (the phenology cube), the
same compositing the RF used.

### The metric

We report **riparian ROC-AUC** because it is threshold-free and is what the RF bar used. Alongside it,
at the model's own operating point:

| held-out reach | riparian precision | riparian recall |
|---|---|---|
| Malpais (arroyo) | 0.834 | 0.712 |
| Farmington | 0.822 | 0.717 |
| Kirtland | 0.788 | 0.476 |
| Aztec/Animas | 0.592 | 0.825 |

Precision/recall vary by fold because the shared decision threshold sits differently on each morphology
(Kirtland under-predicts, Aztec over-predicts) — which is *why* AUROC, being threshold-free, is the fair
comparison.

### Where a reviewer *should* attack this — the honest limitations

1. **The two AUCs are not pixel-identical.** The FM's AUROC is **one-vs-rest multiclass** (riparian vs
   water/agriculture/other) over its labeled pixels; the RF's was **2-class** (riparian vs
   corridor-negatives). Both are "riparian ROC-AUC on the held-out reach" and the trend is unambiguous —
   but a **+0.33 arroyo gap** dwarfs any definitional nuance, whereas the ±0.01–0.03 river-reach
   differences are **within the zone where the metric mismatch matters**, so "ties on rivers" is the
   defensible reading, not "RF slightly wins."
2. **The best checkpoint was pre-unfreeze on every fold** (e.g. epoch 13 for Malpais). The full
   fine-tune *overfit* this scarce-label regime — the frozen-encoder + trained-decoder stage was best.
   Reported numbers are from that best checkpoint (correct behaviour), but it says the 207 M-param
   encoder is not being fully exploited here; more/broader labels would likely help.
3. **Significance is not yet computed.** The pre-registered contract asks for a **cluster-aware
   (reach-block) bootstrap CI** on the FM−RF difference. The point estimates are clear (especially the
   arroyo), but the river-reach deltas are small enough that "tie" should be read as *not yet
   distinguished*, not *proven equal*.
4. **One year, one label vintage.** Fit on 2020 imagery against NMRipMap (NAIP-2020) labels. Transfer
   across *time* and *sensor* are separate, already-measured axes
   ([3A](2026-07-18-phase3a-cross-sensor-result.md), [3B](2026-07-18-phase3b-temporal-result.md)); this
   result is about transfer across *morphology*.

---

## The deployable maps — and a warning about "looks better"

Both models, trained on all four reaches, were deployed over two reaches to *see* the difference
([arroyo](fm-vs-rf-malpais.html) · [Bloomfield river](fm-vs-rf-bloomfield.html)). The arroyo map is the
vivid win — FM green tracking the corridor, RF a handful of specks. But the Bloomfield map carries a
lesson. By eye the FM looks *more accurate* there; scored against the NMRipMap truth on a common 10 m
grid, it is not:

| Bloomfield (river) | precision | recall | IoU |
|---|---|---|---|
| FM | 0.55 | 0.70 | 0.45 |
| RF | **0.61** | 0.70 | **0.48** |

Recall ties; the **RF slightly wins precision and IoU**. What reads as "more accurate" is the FM's
**coherence** — it draws tidy, corridor-shaped patches (and a bit more area), while the per-pixel RF
speckles. **Tidiness is not accuracy.** The FM's measurable accuracy edge is confined to the arroyo; on
rivers it ties or slightly trails. That distinction is the whole point of scoring instead of eyeballing.
(Caveat: NMRipMap truth is sparse — 5.7% of the AOI — so absolute precision is a lower bound; the
*relative* FM-vs-RF ordering is the reliable part.)

## What it means for the product

The deploy decision ([spec](specs/2026-07-19-fm-vs-rf-deploy-decision.md)) was written to be settled by a
number, and it is: **GO — the foundation model ships for the deployable map.** But the *reason* reshapes
how it ships:

- For **well-sampled river corridors**, RF is a perfectly good, far cheaper model — worth keeping as the
  fast path.
- The foundation model's value is **concentrated on under-represented morphologies** (arroyos, and by
  extension any reach type scarce in the training labels). That is where the GPU spend pays for itself.

The pragmatic product is therefore **not "replace RF with the FM everywhere."** It is **"RF by default,
the foundation model where morphology is scarce"** — and the single most valuable next investment is
**more diverse labeled reaches**, since the FM's edge is precisely its ability to convert them into
transfer.

## Reproduce

On a CUDA GPU with the datasets built ([`materialize_reach.py`](../experiments/riparian_extent/materialize_reach.py)):

```bash
cd experiments/riparian_extent
export PYTHONPATH=../../python-etl
python build_loro_dataset.py --dest dataset_loro          # combine 4 reaches, tag by reach, rasterize
for reach in malpais farmington kirtland aztec_animas; do
  python run_loro.py --dest dataset_loro --hold-out $reach --fit   # fit on 3, test held-out once
done                                                       # read test_riparian_classification/riparian_auroc
```

Full runbook, including the GPU-box setup:
[`LAUNCH-LORO.md`](../experiments/riparian_extent/LAUNCH-LORO.md).
