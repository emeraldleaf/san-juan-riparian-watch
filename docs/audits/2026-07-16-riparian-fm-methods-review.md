# Methods review — riparian & invasive EO methods others have used, and what to expand on

**Date:** 2026-07-16 · **Method:** systematic literature search (OpenAlex, 16 method-scoped
queries → 320 unique works → 19 primary sources read at abstract level) · **Verdict:** 🟡
**Contribution SURVIVES; several concrete techniques are adoptable now, and one result is a direct
warning to the FM plan.**

> **Provenance — read this first.** Built from OpenAlex metadata + **abstracts**, not full-text
> reads (two closest primary sources — Meng 2012 beetle-defoliation, and the CSU/Walton tamarisk
> report — are paywalled; the standing TODO to `/paper-audit` the Walton report before Phase 2 is
> unchanged). Every claim below is **secondary** until the source PDF is read. This complements the
> `2026-07-14` prior-art audit, which asked "does the *product* exist"; this asks "what *methods*
> have others used, and which can we lift or extend." Contributed by an external analysis session as
> reference for the repo agent — nothing here was committed to the pipeline.

## Bottom line for the plan

1. **The FM-fine-tune framing still survives** as the contribution — no source fine-tuned a
   geospatial foundation model on riparian extent **and** invasive riparian species with staged
   weak→strong supervision. Consistent with the `2026-07-14` audit.
2. **But a 2025 result is a direct challenge to the FM premise and should be treated as a risk, not
   ignored:** on cross-geography multispectral time-series transfer, *simple spectral-temporal
   representations beat modern geospatial-FM embeddings* (`Tong2025_CropGlobe`). Your own retracted
   frozen-Nano result (F1 0.065) already rhymes with this. **The extent control is exactly the
   experiment that adjudicates it** — keep the RF pixel-level baseline (0.90–0.92) as the gate, and
   report the FM-vs-simple-features delta honestly whichever way it falls.
3. **Three techniques are adoptable now, at low cost, and each maps to an open decision in your
   Phase-0 record.**

## The method landscape — what others actually did

| Theme | Sources | What they did | Relevance to our plan |
|---|---|---|---|
| **Phenology windows as the invasive discriminator** | `Ai2017_Spartina`, `Somers2012_HawaiiSep`, `Meng2012_BeetleDefol` | Identify *specific* phenological stages (senescence Nov–mid-Dec; green-up Apr–May) and build features from those windows, not the whole year. Somers quantifies native-vs-invasive separability with a Separability Index over a 4-yr Hyperion series. | Direct support for your late-senescence Tamarix thesis — **and** a method: don't feed 12 flat mosaics, engineer/weight the senescence and green-up windows. Your `validate_layer.py` already restricts to peak-season; extend the same idea to a **senescence-window channel.** |
| **Beetle defoliation is mappable — on the San Juan specifically** | `Meng2012_BeetleDefol` | Landsat-5 multitemporal, 2006–2010, Disturbance Index vs Random Forest, mapping *Diorhabda* defoliation along Green/Colorado/Dolores/**San Juan** rivers. | Precedent that defoliation *state* is detectable in your exact AOI with change-based features. Tempers the Phase-0 "defoliation-as-state is a risky, largely un-validated head" — it's risky, but not unprecedented; adopt DI-style change features as a baseline before an FM head. |
| **Invasive riparian species via S2 + RF, year-matched** | `Courtney2024_RussianOlive`, `Vorster2018_CSUpoints` | Russian-olive mapped along the Powder River from field points + S2 spectral variables + RF (R²=0.64), **2020 labels/imagery matched**; CSU 2017 occurrence/absence points (3,476 records incl. live/dead/**defoliated** status). | The closest species analogues. Courtney validates your year-matching rule independently. The CSU points carry a **defoliation status field** — the label you need to disentangle senescence from beetle-browning, and the pool your beetle-ADR already references. |
| **Self-supervised / FM pretraining for label scarcity** | `Yuan2020_SSLSITS`, `Cong2022_SatMAE`, `Jakubik2023_Prithvi`, `Tseng2023_Presto`, `Wang2024_FGMAE`, `Dumeur2025_ALISE` | Masked-autoencoder / masked-observation pretraining on unlabeled SITS, then fine-tune on small labeled sets. Presto is pixel-timeseries and *tiny*; ALISE handles irregular/unaligned SITS; SatMAE groups bands with distinct spectral encodings. | These are the alternatives/complements to OlmoEarth. **Presto is the important one for you** — pixel-timeseries, runs on CPU, competitive with far larger models — a legitimate cheap baseline/contender to OlmoEarth-Base that de-risks the whole GPU bet. |
| **Decoder / architecture choice for per-pixel SITS** | `Zhao2022_ArchEval`, `Tzepkenlis2023_UTAE`, `Cong2022_SatMAE` | Head-to-head of CNN/3D-CNN/LSTM/ViT for pixel-level Sentinel time series (3D-CNN & ViT best at preserving temporal info); U-TAE = temporal-attention U-Net for per-pixel land cover. | Independent evidence for your Phase-0 **Open Decision #1** (pooling → per-pixel decoder). The literature is nearly unanimous that extent wants a **per-pixel/segmentation head (UNet/U-TAE)**, not one-label-per-window pooling. Adopt `UNetDecoder`; consider U-TAE-style temporal attention. |
| **Corridor-first & hierarchical masking** | `Singh2020_Hierarchical`, `Vanderhoof2023_S1S2water` | Singh: 3-stage hierarchical classifier (water → aquatic veg → target species) to control false positives over large extents. Vanderhoof: S1+S2 fused, open vs **vegetated** water at 20 m across CONUS. | Supports your corridor-constrained-negatives design and points to **S1/S2 fusion** for the wet-corridor mask. A hierarchy (corridor → woody riparian → introduced) is a cheaper, more debuggable structure than one flat multiclass head. |
| **Dryland riparian health / groundwater controls** | `Downs2024_DrylandHealth`, `Jarchow2020_Shiprock` | NDVI-vs-abiotic GAMs over multi-decadal series; Jarchow studies vegetation-groundwater-ET at **Shiprock, NM** (your lowland tile's reach) after biocontrol invasion. | Method for the Stage-3 "condition/change" product: relate NDVI trajectories to groundwater/high-flow history. Jarchow is essentially a ground-truth ecohydrology study *inside your AOI* — a validation and interpretation anchor. |

## What to adopt / expand on — concrete, ranked by value/cost

1. **Add a Presto baseline before (or beside) the OlmoEarth-Base fine-tune.** `Tseng2023_Presto` is
   pixel-timeseries, CPU-runnable, and competitive with large FMs at a fraction of the compute.
   Given `Tong2025_CropGlobe` (simple temporal features beat FM embeddings on transfer) and your own
   retracted frozen-Nano result, Presto is the honest "is the FM actually earning its GPU?" control —
   cheaper and more diagnostic than RF alone. **Expansion:** three-way extent bench — RF (hand
   features) vs Presto (light SSL) vs OlmoEarth-Base (heavy FM), same folds, same 2020 cube.

2. **Move to a per-pixel decoder (UNet / U-TAE), and engineer a senescence-window channel.**
   The decoder question (Phase-0 Open Decision #1) is settled by the literature toward per-pixel
   segmentation. Beyond that, the phenology papers say the discriminator lives in *specific windows*
   — so give the model an explicit **late-season (Sep–Oct) senescence contrast** feature, not just
   12 undifferentiated mosaics. This is the mechanistic Tamarix signal, made legible to the model.

3. **Use the CSU 2017 defoliation-status labels to build the beetle-confound control.**
   `Vorster2018_CSUpoints` records live/dead/**defoliated** status. That is the field label that lets
   you separate "Tamarix senesces late" from "defoliated Tamarix browns early" — the confound your
   beetle-ADR flags as having no clean spatial control. Adopt DI-style change features
   (`Meng2012`) as the defoliation baseline; treat the FM defoliation head as the upside, not the
   floor.

4. **Adopt a hierarchical (corridor → woody → introduced) structure and consider S1/S2 fusion for
   the wet mask.** `Singh2020_Hierarchical` + `Vanderhoof2023_S1S2water` show a staged classifier
   controls false positives over large extents better than one flat head, and that S1 SAR adds a
   cloud-independent water/structure signal your current optical-only cube lacks.

## Risks this review surfaces (record now)

- 🔴 **The FM may not beat simple spectral-temporal features on transfer** (`Tong2025_CropGlobe`).
  Do not assume OlmoEarth wins; the extent control + a Presto arm are what turn this from an
  assumption into a measured result.
- 🟡 **Every FM analogue is trained on abundant labels or benign targets** (crops, floods, mangrove).
  None is a 332-polygon, narrow-corridor, dryland species task. Label scarcity is your real
  adversary; the label-efficiency literature (SSL/Presto) is the relevant countermeasure, not model
  size.
- 🟡 **Paywalled primary sources not yet read:** `Meng2012_BeetleDefol` (closed) and the CSU/Walton
  report. The `/paper-audit` of Walton before Phase 2 remains the highest-value direct read.

## References (19 primary sources; full corpus of 320 in the companion CSV)

| Key | Year | Cited | DOI |
|---|---|---|---|
| Ai2017_Spartina — phenology-based invasive mapping | 2017 | 40 | 10.1117/1.jrs.11.026020 |
| Somers2012_HawaiiSep — native/invasive spectral separability, time series | 2012 | 69 | 10.3390/rs4092510 |
| Meng2012_BeetleDefol — tamarisk defoliation, Landsat, incl. San Juan | 2012 | 26 | 10.2747/1548-1603.49.4.510 |
| Courtney2024_RussianOlive — Russian olive, S2 + RF, year-matched | 2024 | 1 | 10.1007/s10530-024-03394-3 |
| Vorster2018_CSUpoints — tamarisk/Russian-olive occurrence + defoliation status | 2018 | 3 | 10.3390/data3040042 |
| Yuan2020_SSLSITS — self-supervised transformer pretraining for SITS | 2020 | 188 | 10.1109/jstars.2020.3036602 |
| Cong2022_SatMAE — MAE pretraining, temporal + multispectral | 2022 | 122 | 10.48550/arxiv.2207.08051 |
| Jakubik2023_Prithvi — geospatial foundation model, HLS | 2023 | 14 | 10.48550/arxiv.2310.18660 |
| Tseng2023_Presto — lightweight pretrained RS timeseries transformer | 2023 | 28 | 10.48550/arxiv.2304.14065 |
| Wang2024_FGMAE — feature-guided MAE for RS | 2024 | 36 | 10.1109/jstars.2024.3493237 |
| Dumeur2025_ALISE — FM for irregular/unaligned SITS | 2025 | 7 | 10.1109/tgrs.2025.3589013 |
| Tong2025_CropGlobe — simple features beat FM embeddings on transfer | 2025 | 0 | 10.48550/arxiv.2509.03497 |
| Zhao2022_ArchEval — CNN/3D-CNN/RNN/ViT for Sentinel SITS | 2022 | 43 | 10.1109/jstars.2022.3219816 |
| Tzepkenlis2023_UTAE — efficient semantic segmentation, U-TAE | 2023 | 50 | 10.3390/rs15082027 |
| Singh2020_Hierarchical — hierarchical invasive-species classifier | 2020 | 69 | 10.3390/rs12244021 |
| Vanderhoof2023_S1S2water — S1/S2 fusion, open vs vegetated water | 2023 | 85 | 10.1016/j.rse.2023.113498 |
| Lake2022_InvasiveCNN — CNN invasive detection, WorldView-2/PlanetScope | 2022 | 74 | 10.1002/rse2.288 |
| Downs2024_DrylandHealth — dryland riparian NDVI-abiotic GAMs | 2024 | 8 | 10.1002/eco.2613 |
| Jarchow2020_Shiprock — vegetation-groundwater-ET at Shiprock NM | 2020 | 11 | 10.1002/hyp.13772 |
