# The arroyo map that didn't hold water — a spatial claim built on unequal extents

**Date:** 2026-08-10 · **Status:** retraction (visual claim) + lesson. The scored metric is
**not** retracted; the map-based spatial narrative built on top of it is.

## The claim

> "Over the held-out Malpais arroyo the FM (green, AUROC **0.889**) tracks the corridor while the
> RF (orange, **0.557**) **fires in one corner.**"

— [`docs/index.md`](index.md), the [`fm-vs-rf-malpais.html`](fm-vs-rf-malpais.html) map, and — newly —
the arroyo swipe in [`story.html`](story.html). It was presented as *visual evidence* that a per-pixel
Random Forest fails on under-represented morphology while the foundation model's spatial context wins.

## The catch

A reviewer asked the obvious question — **"why does the RF only fire in one corner?"** — and the answer
did not survive inspection. Comparing the three map layers' extents:

| layer | bbox span (°) | features | covers |
|---|---|---|---|
| `fm_malpais` | 0.128 × 0.085 | 2108 | the full arroyo |
| `truth_malpais` | 0.124 × 0.084 | 599 | the full arroyo |
| **`rf_malpais`** | **0.023 × 0.038** | 207 | **the southern sliver only** |

The RF layer covers roughly a **fifth of the width and under half the height** of the FM and truth
layers, cut off well inside the mapped arroyo on three sides. The exact cause — a partial prediction
run, a clipped export, or a different grid than the FM/truth tools used — is **not recovered here**.
That it was never checked before the claim shipped is the point.

## Why the visual is invalid

**Overlaying two prediction layers of unequal spatial extent and reading "one fired here, the other
everywhere" confounds model behavior with export coverage.** You cannot attribute the difference to the
model when the layers don't even cover the same ground.

And the science doesn't fit the story either: a per-pixel model scoring **AUC 0.557 — barely above the
0.5 random line** — produces a spatially *diffuse* probability field, not a tight blob in one corner. A
compact, edge-aligned cluster is far more consistent with a **coverage boundary** than with the
morphology-domain-shift mechanism the map was used to illustrate.

## What still stands

The **scored transfer metric is valid and unaffected**: RF **0.557** vs FM **0.889** AUROC, computed on
the *shared labeled point set* from the leave-one-reach-out experiment (see
[the diverse-reach transfer result](2026-07-20-diverse-reach-transfer.md)). The morphology
domain-shift *interpretation of that metric* is independently supported — each reach is separable
in-domain at CV ≈ 0.90 while the decision boundary doesn't transfer across morphology. **What is not
supported is the map as independent visual proof of that mechanism.** The number is the evidence; the
picture was decoration that got promoted to evidence.

## The lesson

1. **A map that overlays layers of different spatial extent is not a comparison.** Add *"do all overlaid
   layers cover the same extent?"* to the map-layer checklist — verify extent parity before drawing any
   spatial conclusion from a multi-layer viz.
2. **A compelling visual is the most dangerous unverified claim** — it reads as self-evident. This one
   propagated across **three surfaces** (`index.md`, `fm-vs-rf-malpais.html`, `story.html`) and into a
   verbal explanation to a reviewer, as established fact, with **zero verification** of what the layers
   actually showed.
3. **It was caught the way the good catches always are here** — a human asked a question that couldn't be
   answered without checking (cf. the merge-gate-theatre finding in [`method.md`](method.md)). The
   grounded agent will happily *explain* the false mechanism too, fluently and with a citation, because
   the mechanism is written down in the corpus. Grounding pins claims to sources; it does not verify that
   the claim matches the pixels.

## Scope check — was this systemic?

Applying the lesson immediately: every multi-layer overlay on the site was checked for extent parity
(max/min layer-width ratio). **The artifact was isolated to Malpais RF.**

| overlay | layers | width ratio | verdict |
|---|---|---|---|
| Bloomfield | `fm_bloomfield` · `extent-bloomfield-rf` · `nmripmap-bloomfield` | 1.1× | ✅ valid — RF covers the full reach |
| Farmington flagship | `present-extent-2020` · `present-invasive-in-corridor` | 1.0× | ✅ valid |
| deep-time epochs | `deep-invasive-{1990,2000,2010,2020}` | 1.0× | ✅ valid — the time slider is sound |
| **Malpais** | `fm_malpais` · `rf_malpais` · `truth_malpais` | **5.6×** | ⚠ the artifact (this note) |

So the Bloomfield FM-vs-RF map — which uses the RF layer the same way — is **legitimate**, because there
the RF export does cover the full reach. The Malpais RF was a one-off partial export, not a systemic
RF-mapping defect. That parity check is now the fix: it belongs in the map-layer checklist.

## Fixes required

- **`story.html`** — remove or reframe the arroyo swipe: either regenerate the RF extent over the
  confirmed full arroyo AOI (`deploy_extent_map.py` malpais bbox `-108.8217,36.8096,-108.6729,36.9508`),
  or drop the misleading spatial overlay and present only the scored bars (0.557 vs 0.889).
- **`index.md`** — strike "fires in one corner"; keep the metric.
- **`fm-vs-rf-malpais.html`** — same caveat, or regenerate at full extent.
- **registry** — record in [`RETRACTIONS.md`](RETRACTIONS.md): the *spatial-visual* claim is withdrawn;
  the LORO metric (0.557 vs 0.889) is not.
