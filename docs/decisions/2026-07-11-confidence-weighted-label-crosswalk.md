# ADR: Treat existing riparian GIS as confidence-weighted weak labels, not ground truth

**Date:** 2026-07-11 · **Status:** Accepted · **Implements:** `python-etl/riparian/labels/`

## Context

Stage 1 has now failed at labelling **twice**, in opposite directions:

1. **Weak labels** (`weak_labels.py`) — "woody ∧ near-water" from ESA WorldCover ∧ io-lulc ∧ NWI.
   Scored **~0.00 F1 on the Animas** tile: irrigated pasture sits within 100 m of water and is
   woody-adjacent, so agriculture was labelled riparian.
2. **NMRipMap "truth"** (`validation/reference.py`) — we then swung to an authoritative map and
   rasterised **every returned polygon** as `riparian = 1`, on a documented assumption that "all
   returned polygons are riparian ... so no attribute filtering is needed."
   **That assumption was false.** NMRipMap classifies its mapping units. On the Animas corridor,
   of 2,513 polygons only **1,360 are woody riparian** — the other 46% included **434 developed,
   299 agriculture, 128 upland, 49 water**. The model was learning *corridor membership*, and
   **agriculture — the exact class the weak labels failed on — was being taught as positive.**

Both failures share one root cause: **a source was treated as ground truth without reading its
classes.** The reported spatial-CV F1 (0.895 / 0.924) therefore measured the wrong target.

Meanwhile the label sources we need are heterogeneous and disagree: CO-RIP is Landsat-era
presence/absence (κ 0.42–0.90 *by ecoregion*), NMRipMap is NM-only but richly classified, CSU's
invasive data is points not polygons, NWI is wetland-not-riparian, NLCD is 30 m.

## Decision

**No source is ground truth. Every label carries a source, a class, and a confidence.**

1. **Normalize** each source's native classes into one vocabulary via an explicit, inspectable
   crosswalk — `python-etl/riparian/labels/crosswalk.csv` (source, source_class, normalized_label,
   confidence, notes). A bad mapping must be visible in a CSV, not buried in a rasterizer.
2. **Never** ingest a source without reading its class attributes. `fetch_labeled()` requests
   `outFields` and keeps the class; unknown codes are **excluded**, never defaulted to the target
   class.
3. **Confidence is a first-class field**, propagated to training (sample weighting) and to output
   (`confidence.tif`, per-reach `confidence`).
4. **Report accuracy per label-provenance and per geography** (NM vs CO), never one blended number
   — because label quality is asymmetric across the basin.

## Consequences

**Good**
- The two failure modes above become structurally impossible: agriculture is now an explicit class
  (`IVD`, 299 polygons on the Animas), not an accident.
- Free ground truth surfaced that we did not know we had: NMRipMap `IC` = *"Lowland **Introduced**
  Riparian Woodland and Scrub"* → **332 tamarisk/Russian-olive polygons on the Animas alone**,
  which gives `health/invasive.py` the labels it never had.
- Sources become *composable*: CO-RIP (CO side) + NMRipMap (NM side) + CSU points (species) +
  NAIP (QA) fuse instead of competing.

**Bad / accepted**
- A crosswalk is a **judgement**, and it is now the most load-bearing artifact in the project.
  It must be reviewed by someone who knows the vegetation, not just the code.
- Confidence values are currently **expert-assigned, not calibrated**. They encode belief, not
  measured reliability. Calibrating them against NAIP is future work.
- Marshes/wet meadows (`IIIA`/`IIIB`) sit awkwardly: riparian but **herbaceous**, and our own
  definition says "woody ... not wetland." We assign them `riparian_herbaceous` and let the class
  schema decide — but this is a defensible-either-way call, not a fact.

## Alternatives rejected

- **Keep using NMRipMap unfiltered as "truth."** Rejected: it is measurably wrong (§Context) and
  it is what invalidated the headline F1.
- **Hand-digitise a training set from NAIP.** Rejected as the *primary* strategy: this is the cost
  bottleneck the entire tamarisk literature runs into. Retained for **validation only**, where its
  cost is justified.
- **Use a single "best" source.** Rejected: none covers the basin. NMRipMap stops at the state line;
  CO-RIP has no species; CSU has no polygons.

## Precedent

Weak/sparse supervision from existing maps is an established EO pattern — e.g. wetland mapping from
sparse annotations with satellite image time series and a temporal-aware SAM
(https://arxiv.org/pdf/2601.11400). Our variant is that the weak labels are **already-published
authoritative GIS products**, mined rather than annotated.

## References

- CO-RIP — https://www.mdpi.com/2220-9964/7/10/397 · https://doi.org/10.5061/dryad.3g55sv8
- CSU/NREL invasive occurrence dataset — https://www.nrel.colostate.edu/improved-rip-maps-crb/
- NMRipMap v2.0 Plus (NM Natural Heritage), GRSJ layers — `L1_Code`/`L2_Code` hierarchy
- Spec: `docs/specs/2026-07-11-stage2-invasives-tamarix.md`
