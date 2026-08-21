# Spec: invasive discrimination — FM-vs-RF LORO (Stage 2), pre-registered

**2026-08-21 · status: proposed (not yet run)**

## Why this exists

The extent LORO ([2026-08-01-fm-vs-rf-loro-result.md](../2026-08-01-fm-vs-rf-loro-result.md))
proved OlmoEarth's **robustness to distribution shift**: on the held-out Malpais reach — a
San-Juan-valley subwatershed unlike the training reaches — the pixel-wise RF collapsed to near-chance
(AUC **0.56**) while the FM held (**0.89**). But that is the **extent** task: *riparian vs not*.

Whether the FM also wins the **harder native-vs-invasive discrimination** is **untested.** During the
2026-08-21 review we nearly shipped an *"the FM handles invasive where the RF can't"* claim inferred
from the extent result — and the native-vs-invasive AUC decomposition on the real scored RF **refuted
it** (RF near-chance on native **0.59** *and* invasive **0.53** alike; the Malpais failure is reach-wide,
not invasive-specific). So this task is a genuinely separate model and claim. **Measure it; do not infer
it.** This spec pre-registers the measurement.

## Task

- **Binary discrimination, within riparian:** invasive (tamarisk / Russian-olive) vs native.
  Positive class = **invasive**.
- **Labels (free, from NMRipMap):** invasive = class **IC** (`riparian_woody_introduced`); native =
  **IA / IB / IE / IIA / IIB**. Score **only on labeled riparian pixels** — this isolates *discrimination*
  from *extent* (extent is the other experiment). An optional second run scores invasive-vs-all for the
  end-to-end product number.

## Protocol — mirror the extent LORO exactly (for comparability)

- **Same 4 reaches** (Farmington, Kirtland, Aztec, Malpais) and the **same 12-month median-mosaic cubes**
  (already materialized + cached — the RF bar is minutes on CPU; the FM fine-tune needs the GPU box).
- **Leave-one-reach-out:** train on 3, score the held-out reach **once**; epoch/threshold selection uses a
  `val` slice of the **three training reaches**, never the held-out one (same unbiased-by-construction
  discipline as the extent run).
- **RF bar:** same 72-band feature stack + `RandomForestClassifier`, restricted to riparian pixels,
  target = invasive-vs-native.
- **FM:** same OlmoEarth recipe (`V1_BASE` + `UNetDecoder`), target = invasive.
- **Metric:** invasive **ROC-AUC** (threshold-free, prevalence-invariant), plus **F1 / precision / recall**
  at the deployment threshold. Per-fold **and** macro-mean.

## Pre-registered decision (mirror the extent contract)

FM ships for the invasive product iff, on the point estimate **and** with a cluster-aware reach-block
bootstrap CI:
- macro-mean invasive AUC ≥ RF **+0.04** with **reach-block-bootstrap CI > 0**, **or**
- it wins the hardest single fold by ≥ **+0.04** significantly with **no other fold regressing > 0.01**.

Report the same honesty the extent result now carries: **n = 4** (weak significance; compute the CI and
say so), the **per-reach trade**, and the GPU cost. No "FM is superior" without the CI.

## Data-reality checks (the lessons that bit us)

1. **Class balance swings hard.** Invasive is ~53% of Malpais riparian but only ~1.7% of Aztec's. A reach
   with too few invasive pixels **cannot be a meaningful held-out fold.** Pre-registered rule, fixed here so
   folds cannot be excluded post-hoc: **N = 500 invasive pixels** is the minimum for a scored fold. Log
   per-reach invasive counts first; a held-out fold with **fewer than 500 invasive pixels** is **reported as
   under-powered and excluded from the macro-mean and the decision** (with its count stated) — it is never
   silently dropped, and never scored as if solid. On the current four reaches, Aztec (~1.7%) is the fold
   most likely to fall under N; if it does, the invasive decision runs on the remaining folds and says so.
   **Both models are scored on the *same* set of powered folds** — the N-based exclusion is computed once,
   from the truth labels, and applied identically to the RF bar and the FM, so it can never advantage one.
   **AUC/F1 always, never accuracy** (a "native everywhere" guess scores high where invasive is rare).
2. **The IC↔IVD confounder.** Tamarisk in the growing season is spectrally close to irrigated agriculture
   (IVD). Since we score within riparian, ag is excluded from the eval — but note it for the deployment
   (invasive-vs-all) run, where ag false-positives are the likely failure mode.
3. **Spatial provenance.** Same `.claude/spatial-provenance.json` gate: any per-reach map layers must be
   co-located and pass `check-layer-colocation.sh`. No repeat of the extent-map mislocation.
4. **Reproduce the RF bar first.** As with extent, reproduce the RF numbers locally (cached cubes) before
   trusting the FM comparison — a faithful RF bar is the pipeline's integrity check.

## What we will know

Whether the FM's distribution-shift robustness **extends to invasive discrimination**, or whether invasive
is its own story (e.g. the FM wins extent but ties on discrimination, or vice versa). Either outcome is a
result. The point is to **know**, the way we now know the extent story — measured, reproduced, CI'd, and
stated with its caveats — instead of inferring a clean narrative that the next test knocks down.

See also: [the extent LORO result](../2026-08-01-fm-vs-rf-loro-result.md) ·
[the FM-vs-RF deploy-decision contract](2026-07-19-fm-vs-rf-deploy-decision.md) ·
[the reach-provenance gap post-mortem](../2026-08-21-reach-provenance-gap.md).
