# Prior-art audit — riparian remote-sensing *methods*, vs. the foundation-model fine-tune

**Date:** 2026-07-14 · **Method:** targeted literature search (not `/paper-audit`; see provenance
note) · **Verdict:** 🟡 **GAP + novelty SURVIVES (narrowed)**
**Outcome:** the FM fine-tune survives as the contribution; the *workflow* around it (corridor
negatives, year-matched labels, overlay-and-look) is **prior-art-supported, not ours to claim** —
so cite it. Two design choices tightened.

> **Provenance — read this first.** This audit is built from a **literature search and synthesis**,
> **not** a direct read of each source PDF. That is the exact failure mode that sank the Evangelista
> audit ("we read the web page, never the report"). So every claim below is marked as **secondary**
> until someone reads the source. The single highest-value direct read is the **CSU/Walton report**
> (§2) — it is the closest procedural analogue to our invasives half and most likely to contain a
> 🔴 THREAT if one exists. Run `/paper-audit` on it before Phase 2.

## The question this audit asks

Not "does a riparian native-vs-invasive *product* exist" — the [Evangelista](2026-07-12-evangelista-2018-csu-nrel.md),
[CO-RIP](2026-07-11-corip-woodward-2018.md), [tamarisk](2026-07-11-tamarisk-detection-established.md)
and [Perkins](2026-07-12-perkins-2025-canyonlands.md) audits already worked that, and narrowed our
claim to *annual, 10 m, beetle-aware, wall-to-wall*. This audit asks the **method** question:

> Has anyone done *what our plan does* — fine-tune a geospatial/EO **foundation model** on riparian
> extent + invasive riparian species with **staged weak→strong supervision**?

**Finding: no exact analogue was found.** The novelty is in the FM-fine-tune framing, not in the
remote-sensing task or the label design — both of which are well-trodden, including in this basin.

## The sources, and what each one supports

| # | Source | Class | What it supports in our design |
|---|---|---|---|
| 1 | **CO-RIP** (Woodward 2018, IJGI) — *already audited* | ⚪ COVERED | **Corridor-first**: defines the riparian domain via **valley bottoms**, then classifies vegetation *inside* it. Direct published support for **"clip negatives to VBET, not desert."** Variable performance across ecoregions supports **per-ecoregion reporting + confidence weighting.** |
| 2 | **CSU / Walton report** — *Mapping Native & Non-Native Riparian Vegetation in the Colorado River Watershed* | 🟡 GAP | The closest procedural analogue for **tamarisk + Russian olive**: field-data compilation, Landsat/Sentinel models, **scene-based** modeling, 2006/2016 mapping. Reports that **S2 vs Landsat Russian-olive models trained on the same data mapped meaningfully different areas, and that evaluation stats looked strong while qualitative maps were wrong** — published support for our **overlay-and-look gate.** |
| 3 | **CSU 2017 occurrence/absence dataset** (MDPI *Data*) | 🔵 CORPUS | Citable **provenance** for the Phase-2 field labels; explicitly published *for* species distribution modeling + RS detection. Does **not** prove S2 can separate tamarisk / Russian-olive / native / defoliated in our AOI. |
| 4 | **Russian olive, Powder River Basin** (Biological Invasions; NASA tech) | ⚫ OUT OF SCOPE (adjacent) | Not San Juan, but confirms Russian-olive is mapped via **field-data + RS modeling**, not generic land cover. |
| 5 | **Furuya et al. 2020** (Remote Sensing) — ML riparian forest w/ Sentinel-2 | ⚪ COVERED | S2 has been used for fine-scale vegetation mapping *inside* riparian zones. Not weak-supervision, not FM. |
| 6 | **Prithvi-EO-2.0, SatMAE**, RS-FM surveys | 🔵 CORPUS | The FM-side analogs: multi-temporal EO pretraining + downstream fine-tuning — but for crops/flood/landslide/land-cover, **not riparian**. Supports the *design pattern*, not the riparian procedure. Ai2's **mangrove** recipe (which our scaffold mirrors) is the nearest task-shape, and mangrove is not a dryland corridor. |

## What it does NOT falsify — the surviving claim

No source did **what our plan does**. The claim, stated narrowly enough to be falsifiable:

> **Prior work has mapped riparian extent and invasive riparian species with RS + ML, including in
> the Colorado River Basin. What appears un-done is using a geospatial foundation model with staged
> weak→strong supervision for riparian corridor extent and tamarisk / Russian-olive transfer.**

That is the contribution: **not "remote sensing of riparian vegetation" — the FM-fine-tune experiment
on top of it.** (Un-done ≠ proven-absent; §2 could still surprise us. Hence the direct-read TODO.)

## What it narrows — stop implying the *workflow* is novel

This audit's real bite: several things our docs present as design *insight* are in fact **published
practice**, and we should cite them as support rather than imply we invented them.

- **Corridor-constrained negatives** — CO-RIP's corridor-first framing. Cite it in the label-layer
  rationale.
- **Metrics-can-lie / overlay-and-look** — the Walton report documents exactly this for Russian-olive
  maps. Our `validate_layer.py` "shift test + eyes" is *good practice with precedent*, not a new idea.
- **Label-year matching** — supported by the CSU temporal framing. Our "never fit against the wrong
  year" rule is right, and not novel.

Being right is not the same as being first. These are validations of our method, and belong in the
spec as citations — which is what the [Prior methods check](../specs/2026-07-12-gpu-finetune-execution-plan.md)
section now records.

## 🟡 GAP — what to adopt / tighten before Phase 1–2

1. **Per-pixel decoder for extent (confirms the open decision).** CO-RIP, Furuya, and the Walton
   work all map pixel/area extent — *spatial*, not one-class-per-window. This is independent support
   for moving off the pooling decoder to `UNetDecoder`. See the Phase-0 record's open decisions.
2. **30 m → 10 m boundary noise.** Stage-A weak labels (CSU tamarisk products are ~Landsat-scale)
   rasterised onto the 10 m grid need a **boundary weight / ignore buffer**, or the model learns a
   30 m-blurred edge. Prior workflows often stay at native scale; we are deliberately mixing, so the
   guardrail is load-bearing.
3. **Beetle-defoliation-as-state is a *riskier extension*, not a solved class.** Tamarisk/Russian-olive
   mapping is established; defoliation *state* is specialised and largely un-validated. Treat it as a
   research risk with its own abort criterion, not a known-good head.

## What changed in the repo

- This audit added to the [falsification log](README.md).
- A **Prior methods check** section added to the
  [GPU fine-tune execution plan](../specs/2026-07-12-gpu-finetune-execution-plan.md), citing CO-RIP,
  the Walton report, and the 2017 dataset as support for the corridor-negative, year-matched,
  overlay-and-look design — framed as precedent, not our invention.
- GAP items 1–3 folded into the plan's open decisions / risk table.
- **TODO (Phase 2 gate):** direct `/paper-audit` of the CSU/Walton report before invasives work.
