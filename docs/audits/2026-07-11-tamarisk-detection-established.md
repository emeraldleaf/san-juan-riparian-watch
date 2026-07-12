# Prior-art audit — tamarisk detection from satellite is established

**Date:** 2026-07-11 · **Method:** *retrospective — found by reading, before `/paper-audit` existed*
**Verdict:** 🟠 **RETRACTS** · **Outcome:** "we detect tamarisk from satellite" is not a contribution
— and the same literature handed us the discriminator that indicted our own harness.

> **Backfilled for the record.** Like the CO-RIP audit, this arrived by reading during the Stage-2
> spec rather than by any gate.

## The literature

| Study | Method | Result |
|---|---|---|
| [Mapping invasive *Tamarix* genotypes with Sentinel-2](https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/) | Sentinel-2 + Random Forest | **87.8% OA** (κ 0.85); SVM 86.3% |
| Landsat-based tamarisk mapping (multiple) | Landsat + RF/SVM | **80–91%** accuracy |
| [Phenological trajectory for saltcedar detection](https://diaorssilab.web.illinois.edu/wp-content/uploads/2023/11/Incorporating-plant-phenological-trajectory-in-exotic-saltcedar-detection-with-monthly-time-series-of-Landsat-imagery.pdf) | **Monthly** Landsat time series (MSAC) | Phenology-guided composite **beats any single scene**; **leaf senescence is the most discriminating stage** |

## What it falsified

**"Can tamarisk be detected from optical satellite imagery?" is a settled question.** It has been
answered, repeatedly, at 80–91% accuracy, since roughly 2005. We are not proving it. Any framing that
presents tamarisk detection itself as the contribution is wrong and must not be published.

## What it gave us — the discriminator

The literature is explicit about *why* it works:

**Phenology — specifically late-season senescence — is the discriminator.** *Tamarix* holds green
canopy after native cottonwood and willow have browned, so the separating signal lives in **how the
spectrum changes across a season**, not in any single scene.

This has three consequences, and the second one cost us:

1. **A single-date classifier is leaving the signal on the table.** Use a dense temporal stack.
2. 🔴 **It indicted our own OlmoEarth harness.** `extract_embeddings` was **mean-pooling encoder
   tokens over the time axis** — averaging away the exact signal the entire literature says is the
   discriminator. We had denied the foundation model the one thing it exists to exploit, and then
   published that foundation models do not help here. See `docs/olmoearth-vs-rf-baseline.md` (the
   result is retracted) — though note the follow-up: **fixing the pooling did not close the gap**, so
   the defect was real but was *not* the cause.
3. **Sentinel-2's 10 m + red-edge matters.** Later confirmed from the other direction by
   [Evangelista et al. (2018)](2026-07-12-evangelista-2018-csu-nrel.md), who report that **Landsat
   cannot resolve the tamarisk phenological signature at all**: *"without a different sensor with
   greater spectral or grain resolution this is a difficult constraint to overcome."*

## What it left open

- Tamarisk detection is established; **native-vs-invasive cover mapped annually, at 10 m, with
  defoliation handled as a state** is not.
- **The biocontrol confound.** *Diorhabda* defoliation makes *Tamarix* brown **early** — inverting the
  late-senescence discriminator this entire literature depends on. No operational classifier we found
  handles it. That is not a footnote; on the San Juan (release 2004–07) it is the central obstacle.
