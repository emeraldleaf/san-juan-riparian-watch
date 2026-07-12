# Prior-art audit — CO-RIP (Woodward et al. 2018)

**Date:** 2026-07-11 · **Method:** *retrospective — found by reading, before `/paper-audit` existed*
**Verdict:** 🟠 **RETRACTS** · **Outcome:** "we built an RF riparian classifier" is not a contribution.

> **Backfilled for the record.** This audit was not run by the command; it happened because someone
> read the literature during the Stage-2 spec, **after Stage 1 had already been built**. That is the
> expensive way to find prior art, and it is the reason `/paper-audit` now exists.

## The paper

> **Woodward, B., Evangelista, P., Vorster, A., et al. (2018).** *CO-RIP: A Riparian Vegetation and
> Corridor Extent Dataset for Colorado River Basin Streams and Rivers.* **ISPRS International Journal
> of Geo-Information** 7(10):397.
> [Paper](https://www.mdpi.com/2220-9964/7/10/397) · [Data (Dryad)](https://doi.org/10.5061/dryad.3g55sv8)

| | |
|---|---|
| Sensor | **Landsat** |
| Extent | The **entire Colorado River Basin** — 637,000 km², 7 states, **including the San Juan** |
| Method | **Valley-bottom delineation (VBET) → Random Forest**, per ecoregion |
| Accuracy | median **κ = 0.80** (range 0.42–0.90 across 12 ecoregions) |
| Products | riparian vegetation raster (0 absence / 100 presence) + valley-bottom polygons |
| Epochs | **One.** A static dataset. |

## What it falsified

Our Stage-1 pipeline is **the same method class**:

| Ours | Theirs |
|---|---|
| HAND valley-bottom envelope | VBET valley-bottom delineation |
| RandomForest on multitemporal spectral features | RandomForest on Landsat spectral data |
| Validated against NMRipMap | Validated per ecoregion |

**Building an RF riparian extent classifier for this basin is not a contribution.** It was published
in 2018, basin-wide, at κ 0.80. CO-RIP is a **baseline to beat and a label source to exploit** — for
Colorado in particular, where NMRipMap does not reach.

## What it left open

- **One epoch.** CO-RIP is a static raster. It says nothing about *change*.
- **Extent without species.** No native-vs-invasive split.
- The wide κ range (**0.42–0.90**) is itself informative: performance is **ecoregion-dependent**, so a
  single blended accuracy number for the basin is misleading — **ours must be reported per region.**

## Consequences in the repo

- Stage 1 was **re-framed from contribution to calibration**: matching the reference for one epoch is
  what makes a time series trustworthy, not a result in itself. See
  `docs/decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md`.
- `docs/STATUS.md` "Positioning" states plainly: *"'We built an RF riparian classifier' is not a
  contribution."*
