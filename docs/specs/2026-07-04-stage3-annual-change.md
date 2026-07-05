# Feature spec — Stage 3: annual change products (extent + health)

**2026-07-04 · feeds the encoding loop.** Builds on the verified Stage-1 delineation
(`riparian_probability` per composite) and Stage-2 condition. See
[Stage-1 spec](2026-07-03-stage1-riparian-delineation.md).

## Goal

Produce **annual** change products for (a) riparian *extent* boundaries and (b) riparian
*health/condition* over the longest feasible record, using consistent annual windows
(leaf-on + baseflow) and confidence gating to avoid false change.

## Resolved open questions (verified on Planetary Computer STAC, our AOI)

- **Start years (longest feasible):** Landsat C2 L2 **1982-12** → present (~44 yr, 30 m) is
  the long backbone; Sentinel-2 **2015-10** (10–20 m); Sentinel-1 RTC **2014-10** (SAR);
  HLS L30 **2017-08** / S30 **2016-01** (harmonized 30 m).
- **Harmonization (Landsat↔Sentinel era):** two tracks.
  - **30 m long-record track (trend backbone):** Landsat C2 L2 (1982–2015) → **HLS**
    (2016+, already cross-calibrates Landsat + Sentinel-2 to 30 m). Ratio indices
    (NDVI/NDMI/NDRE) are the most cross-sensor-comparable; compute the *same* band math
    every year. This track drives multi-year trend.
  - **10 m modern-detail track (2015+):** Sentinel-2 (+ Sentinel-1). Best corridor detail;
    shorter history. Tagged with era metadata so comparisons stay honest.
- **Storage:** annual probability/health **rasters → COGs** (cloud-native, tileable to the
  map); **reach × year summaries + change + trend → PostGIS gold tables** (queried by the
  API for "top-N reaches by loss/decline" + time-series charts); extent masks stay as vector
  polygons in `silver` per year (as today). Rationale: the web app's reach tables + charts
  come from PostGIS; raster overlays from COGs.

## Annual windows (two per year, per AOI, lat/elevation-banded)

- **Leaf-on** (productivity): peak canopy vigor.
- **Baseflow / late-summer** (persistence): groundwater-subsidy signal — separates true
  riparian from seasonal uplands. San Juan Basin default: leaf-on Jun–Aug, baseflow Aug–Sep.
- The *same* windows for every year with data.

## Outputs

- **Annual state (per year Y):** `riparian_probability_Y`, `riparian_mask_Y`,
  `health_score_Y`, `qa_Y` (valid-obs counts, cloud-gap %, SAR availability).
- **Annual change (Y vs Y−1):** boundary `gain_Y` / `loss_Y` / `stable_*_Y`; health
  `health_delta_Y`, `health_decline_flag_Y`, `health_improve_flag_Y` (restricted to extent).
- **Multi-year trend (per reach):** `riparian_area_trend` + `health_trend` (Theil–Sen slope),
  optional `trend_significance` (Mann–Kendall).
- **Reach × year summaries:** `%riparian_cover_Y`, `riparian_area_Y`, `median_health_Y`,
  `qa_confidence_Y`; plus `Δriparian_area_Y`, `Δhealth_Y`.

## Anti-false-change principles (load-bearing)

- **Comparable composites:** same band math + QA every year; robust reducers (median /
  percentile), never single-scene.
- **Confidence gating:** do NOT emit gain/loss or health delta when *either* year is below a
  coverage threshold. Store the QA fields alongside every layer.
- **Anti-jitter:** retain the continuous `riparian_probability_Y` (not just the mask);
  spatial + confidence smoothing; optional 2-consecutive-year persistence before calling a
  boundary crossing. This prevents threshold jitter from masquerading as real change.

## How it reuses what exists

`run_delineation(date_range=...)` already produces `riparian_probability` for any window —
so an **annual state layer is one call per year per window**. Stage 3 wraps it in a
year loop + composite/QA discipline + change math. Health reuses the Stage-2 indicators on
the Stage-1 mask.

## Invasive species (tamarisk / Russian olive) in health

Woody invasives are the dominant riparian degradation driver in the San Juan Basin —
**tamarisk (saltcedar, *Tamarix* spp.)** and **Russian olive (*Elaeagnus angustifolia*)**
(Siberian elm a distant third). Invasive dominance is a **negative** health signal (poor
native habitat, altered hydrology, elevated fire risk), so it enters the health score as a
penalty and ships as a standalone cover product.

- **Labels (confirmed available):** NMRipMap `L3_Name` / NVC fields tag invasive stands —
  e.g. "Lowland Native-Introduced Tamarisk Deciduous Riparian Forest", "Russian
  Olive-Tamarisk Introduced Riparian Woodland and Scrub", NVC "Interior West Ruderal
  Riparian Forest & Scrub". Rasterize: `invasive=1` where L3_Name/NVC matches
  Tamarisk/Russian-Olive/Introduced/Ruderal (use the cover-fraction fields — classes are
  often mixed "Native-Introduced"), native riparian `=0`, within the Stage-1 extent.
- **Classifier:** RF (or OlmoEarth) on the *same* multi-temporal features — phenology is the
  discriminator (tamarisk late green-up/senescence; Russian olive silvery low-NDVI foliage;
  natives earlier). Applied only inside the riparian mask → per-pixel invasive probability.
- **Products:** `invasive_cover_pct` per reach (mirrors `%riparian_cover`) + per-pixel
  invasive layer.
- **Health integration:** `health = f(greenness, moisture, persistence, structure) ×
  (1 − w·invasive_fraction)`; `invasive_cover_pct` also reported standalone.
- **Stage-3 change:** annual `invasive_cover_pct_Y` → **spread detection** (tamarisk/Russian
  olive expansion per reach over time) — a top-value manager product.
- **Honest scope:** start **binary invasive-vs-native** (~75–85% realistic); species-level
  split (tamarisk *vs* Russian olive) is a stretch. NMRipMap labels are **NM-only** — the
  classifier trains/validates on NM and extrapolates to CO (the reference-layer seam).

## Phased implementation

- **Phase A — MVP (Sentinel-2 modern era, 1 tile):** add `year` (+ `window`) to
  `silver.riparian_extent`; annual driver runs delineation per year (leaf-on) for Malpais
  2019–2023 → per-year probability/mask; compute per-pixel gain/loss + reach-level Δ into a
  `gold.reach_change` table. Verify the state→change loop end-to-end.
- **Phase B — QA + anti-jitter:** add coverage/cloud-gap QA per composite; gate change on
  confidence; 2-year persistence for boundary crossings.
- **Phase C — Landsat backbone (deep history):** add a Landsat/HLS 30 m composite path;
  produce the 1982+ annual record on the trend track; Theil–Sen per-reach trend.
- **Phase D — annual health (Stage 2) + change:** annual `health_score_Y` on the mask
  (greenness + moisture + persistence + structure), **penalized by invasive cover**;
  `health_delta` + decline/improve flags; trend.
- **Phase D2 — invasive cover:** train the invasive-vs-native classifier on NMRipMap labels;
  `invasive_cover_pct` per reach; wire into the health penalty; annual → **spread detection**.
- **Phase E — web app:** reach time-series charts + "top-N loss / top-N decline" tables +
  annual raster overlays (COGs).

## Acceptance criteria (initial)

- Annual state products end-to-end for the maximum feasible record.
- Annual change (gain/loss + health delta) with confidence gating.
- Reach summaries support "Top-N reaches by riparian loss", "Top-N by health decline", and
  time-series charting in the UI.

## Deferred

- Breakpoint detection (BFAST-style) — later iteration unless abrupt-disturbance detection
  is explicitly needed.
