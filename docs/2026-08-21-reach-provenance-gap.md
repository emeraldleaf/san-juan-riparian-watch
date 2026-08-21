# The reach-provenance gap: a headline result rested on mismatched extents

**2026-08-21 · post-mortem + prevention plan**

> **⚠ Retracted / under review (2026-08-21):** this document *is* the retraction of the
> "desert arroyo rescue" (RF 0.557 → OlmoEarth 0.889). That reach is the **river-dominated
> subwatershed** "Malpais Arroyo–San Juan", the imaged extent excludes the arroyo, and
> **attribution to arroyo morphology is unverified**. See
> [RETRACTIONS.md](RETRACTIONS.md) → `arroyo-rescue-attribution-2026-08-21`.

## Summary

The project's headline novelty claim — that Ai2's OlmoEarth foundation model *rescued a desert
arroyo the Random Forest was blind to* (transfer AUC **0.557 → 0.889**) — rested on a reach that is
**not an arroyo**, evaluated over an **extent that excludes the arroyo**. Five artifacts all carried
the label "Malpais" and were silently assumed to describe the same place. They do not:

| artifact | what it actually is | extent |
|---|---|---|
| defined reach (`validate_reach.py`) | HUC12 140801051001 **"Malpais Arroyo–San Juan"** | `-108.8217, 36.8096, -108.6729, 36.9508` |
| imaged windows (`dataset_malpais`, **the scored set**) | the **southern San Juan valley** only, 328 windows | `-108.8239, 36.8071, -108.6962, 36.8930` |
| `truth_malpais.geojson` (display) | San Juan-valley NMRipMap subset | ~south |
| `fm_malpais.geojson` (display) | OlmoEarth on the **San Juan mainstem** | ~south-west |
| `rf_malpais*.geojson` (display) | RF on a **different sub-area** | ~south-east |

The **defined reach extends ~6 km north (up the wash) beyond the imaged windows** — and the LORO
scores exactly the imaged windows (`run_loro.py` tags the held-out reach's 328 windows `split=test`).
So **0.557 / 0.889 is a hard-*river*-reach transfer number, not an arroyo result.** The map layers
render three different sub-areas; the ground truth and both models sit on the San Juan; the arroyo the
whole story rests on was never imaged, never labeled, never scored.

## How it was found — by eye, not by a gate

Nothing mechanical caught this. It surfaced on 2026-08-21 when the project author opened the "ask the
map" agent, overlaid RF / FM / NMRipMap-truth on satellite, and simply *looked*:

1. "This looks like the San Juan River, not Malpais." — the FM layer traces the mainstem past US-491.
2. "The RF shows almost nothing and the FM doesn't go up the wash." — the two models sit on different
   features.
3. "The riparian up the wash isn't in the FM layer at all." — truth and model disagree on *which water*.
4. "The 12 months of imagery don't go up the wash." — the imaged extent stops short of the arroyo.

Each observation was a hypothesis; each was then checked against the data (bbox overlay, window-vs-truth
coverage, the `run_loro` split). The checks confirmed the labeling was inconsistent and the arroyo
un-imaged. **A ten-second look at the map did what months of gated CI did not.**

## Root cause

**No artifact tied the pieces of a spatial result together, and nothing verified they agreed.** "Malpais"
was a *name*, reused across a HUC12 bbox, an rslearn dataset, three display GeoJSONs, and a truth file —
each materialized by a different tool (`materialize_reach.py`, `build_loro_dataset.py`,
`deploy_extent_map.py`, the extent exporter), at a different extent, with **no manifest asserting they
describe the same ground.** The name did the work a provenance record should have done. Once the RF-vs-FM
*maps* were exported from different sub-areas (already partially retracted 2026-08-10 as an "unequal
extent" artifact), and the reach name ("arroyo") no longer matched the imaged geometry (river), the
story wrote itself — and read as true, because every *textual* check passed.

## Why every existing gate missed it

The encoding-loop method has real teeth — canon-size limits, diagram pairing, stale-ref audits after
`git mv`, the tombstones registry, and the retraction registry that forces a withdrawn *claim* to be
retracted everywhere. **Every one of them enforces file *shape* or *claim* consistency in text.** Not
one can see that:

- a result's **display extent ≠ its scored extent**,
- two layers in a "head-to-head" cover **different ground**,
- a reach named **"arroyo"** is geometrically a **river**,
- the **imagery that trained a model excludes the region the claim is about.**

The method mechanized **textual honesty**. It has **no tier for spatial / data-provenance honesty** — and
a map can lie while every sentence about it is internally consistent. This is the same failure mode the
method was built to kill (a retracted result living on the public site), one layer down: a *mis-grounded*
result living on the public site, with no mechanism able to notice because the sentences matched the
(wrong) maps.

## Prevention — a spatial / data-provenance tier

Five gates, in rough order of leverage. The first three are cheap and catch this exact class.

1. **Result provenance manifest (required).** Every published spatial result declares, machine-readably,
   the reach name, the **defined bbox**, the **scored/imaged extent**, the label source + vintage, and
   the exact asset files. One record, checked in. A comparison with no manifest cannot ship.

2. **Co-location gate (CI).** For any result that overlays layers as a comparison (truth / RF / FM), a
   script asserts their bounding boxes **overlap ≥ some fraction** (e.g. IoU > 0.8). Fails the build when
   "head-to-head" layers describe different ground. *(This exact check, run by hand today, is what
   surfaced the problem.)*

3. **Extent reconciliation.** The manifest's **defined bbox, imaged extent, label extent, and display
   extent must agree** within tolerance — or the discrepancy must be stated in the manifest. The
   defined-vs-imaged mismatch here (~6 km) would have failed on sight.

4. **Name ↔ geometry check.** A reach named `* Arroyo` / `* Wash` whose geometry is dominated (by area or
   by the NHD FTYPE it overlaps) by a river/mainstem is flagged. Names must earn their morphology claim.

5. **"Draw your extent" discipline.** Any published spatial result ships with its bbox and scored extent
   **renderable on the map** (the inspection layers added to `/map` on 2026-08-21). A reviewer must be
   able to *see* what area a number covers in one click. Un-viewable extent = un-reviewable claim.

Two of these are already partly real: the `/map` page now carries **"NMRipMap truth · Malpais"** and
**"Experiment bbox (defined vs imaged)"** layers (#5), and the co-location check (#2) exists as a
one-off script. The next step is to make #1–#3 mechanical, in the drift-gate tradition — *a gate nobody
runs is documentation, not enforcement.*

## The broader lesson

The method's own thesis — *rules encoded across surfaces, kept from drifting by mechanical hooks* — held
for text and broke for space. **Textual consistency is not correctness.** A pipeline that maps the Earth
needs its honesty gates to reach *the pixels*: to check that a result's data, labels, imagery, score, and
map all describe the same ground, and that a reach is what its name says it is. Until they do, the most
dangerous error is not a wrong sentence — it is a right sentence about the wrong place.

See also: [RETRACTIONS.md](RETRACTIONS.md), [2026-08-10-arroyo-map-extent-artifact.md](2026-08-10-arroyo-map-extent-artifact.md)
(the earlier, narrower catch), [method.md](method.md).
