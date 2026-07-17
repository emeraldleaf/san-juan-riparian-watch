# Handoff note — Malpais reach: separability & corridor resolvability (external session)

**Date:** 2026-07-16 · **Status:** reference only — computed off-repo, NOT with `validate_layer.py`.
**For:** the repo agent, as a second data point on the Phase-0 "one reach, not the basin" caveat.

## Context
The Phase-0 record reports separability **AUC 0.752** on the **Farmington** reach and flags: *"one
reach, not the basin … the number to watch is whether AUC 0.752 holds on the narrow headwater
corridors."* This note adds a **second reach — Malpais Arroyo–San Juan (tile 140801051001, NM)** —
from an independent Sentinel-2 2020 phenology audit.

⚠️ **Not directly comparable to 0.752.** These numbers come from an *ad-hoc* corridor-vs-upland
harness (distance-to-NHD-mainstem bins), **not** `validate_layer.py` (no VBET clip, no 3× cap,
water not explicitly excluded, corridor defined by distance not NMRipMap negatives). Treat as
*indicative that signal exists on this reach*, not as a validated AUC. **To make it comparable, run
`validate_layer.py` on this tile** — that is the recommended next step.

## What was measured (Sentinel-2 2020, corridor ≤60 m vs upland 300–1500 m from the San Juan main stem)

| Metric | Corridor | Upland | Δ | AUC (raw index, corridor vs upland) |
|---|---|---|---|---|
| Peak NDVI (JJA) | 0.307 | 0.064 | +0.242 | 0.78 |
| Dry-season NDVI floor (DJF) | 0.220 | 0.083 | +0.137 | 0.77 |
| **NDVI annual amplitude** | 0.192 | 0.030 | +0.161 | **0.85** |
| Peak NDMI (canopy water) | +0.027 | −0.177 | +0.203 | 0.84 |

Reading: on Malpais, a *single hand-computed index* already gives corridor-vs-upland AUC 0.77–0.85 —
consistent with the "plausible band" the validator expects, and the groundwater-subsidy dry-season
floor (0.22 vs 0.08) is clearly present. Signal holds on this reach.

## Corridor resolvability — evidence for Phase-0 Open Decision #2 (S2 10 m vs Landsat 30 m)
Ring-median JJA NDVI vs distance from centerline: **0.196 @15 m → 0.087 @35 m → 0.064 (upland
background) by ~70 m.** Vegetated band ≈ 40–50 m per side (~80–100 m total):

- ~8 px wide at 10 m (Sentinel-2)
- ~4 px at 20 m
- **~3 px at 30 m (Landsat)**

Aggregate corridor-vs-upland NDVI *contrast* is nearly resolution-invariant (0.338 → 0.333 from
10→30 m — a ring-median averages many pixels), **but spatial delineation degrades**: at 30 m the
corridor edge and its separation from adjacent irrigated fields blur (see figure). Implication for
Decision #2: **Landsat can likely track corridor greenness *trends*, but 10 m is needed to
*delineate* the corridor and to keep river phreatophytes from mixing with irrigated agriculture** —
which matters most for the Tamarix/native split, where field NDVI is the confound.

## Caveat carried from the maps
Irrigated agriculture on the valley floor also shows high NDVI, high amplitude, positive NDMI — a
single index cannot separate riparian from cropland. This is *why* the multi-feature RF + FM are the
right tools; the audit confirms the signal exists, it does not replace the classifier.

**Companion artifacts:** phenology maps + width profile + resolvability figure, and the 12-month
20 m index cube (NDVI/NDMI/NDRE/kNDVI/EVI), saved in the same session.
