# Spec — Stage 2: Invasive vs native riparian cover (Tamarix), and its change

**Status:** Draft · **Date:** 2026-07-11 · **Supersedes:** nothing (no Stage-2 spec existed)
**Implements:** `python-etl/riparian/health/invasive.py` (which until now had no spec and no ground truth)

---

## 1. Thesis

> A reach is not healthier just because it is greener.

Total riparian cover can *increase* while the corridor *degrades* — because the increase is
Tamarix (saltcedar) replacing cottonwood and willow. A monitoring product that reports only
"riparian vegetation up 8%" can therefore report ecological decline as success.

Stage 2 must separate:

```
tamarix / introduced woody cover
native (and other) woody riparian cover
```

and track each **through time, per reach**, so the system can say *"total cover rose, but the
rise was Tamarix"* rather than *"the corridor is recovering."*

This is the single highest-value thing this project can do, because it is the distinction
managers actually act on (removal, revegetation, biocontrol monitoring) and it is the one the
existing basin-wide products **do not** provide (§3).

---

## 2. What already exists (and why we are not duplicating it)

This section is deliberately blunt. Two of our current components substantially reproduce
published work, and we should say so rather than claim novelty we do not have.

### 2.1 Riparian extent mapping — **already solved at basin scale**

**CO-RIP** — Woodward et al., *ISPRS IJGI* 7(10):397, 2018.
[Paper](https://www.mdpi.com/2220-9964/7/10/397) ·
[Data (Dryad)](https://doi.org/10.5061/dryad.3g55sv8)

- Riparian **corridor extent + riparian vegetation presence/absence** for the **entire
  Colorado River Basin** (637,000 km², 7 states) — *including the San Juan*.
- Method: **valley-bottom delineation → Random Forest on Landsat spectral data**, per ecoregion.
- Accuracy: **median kappa 0.80** (range 0.42–0.90 across 12 ecoregions).
- Vegetation raster: `0` = absence, `100` = presence. Valley bottoms: polygons.

> **Honest consequence for us:** our Stage-1 RF baseline is *the same method class*. Our HAND
> valley-bottom envelope ≈ their valley-bottom delineation; our RF-on-multitemporal-spectral
> features ≈ their RF-on-Landsat. **"We built an RF riparian classifier" is not a contribution
> — CO-RIP did it basin-wide in 2018.** We should treat CO-RIP as a *baseline to beat and a
> label source to exploit*, not as something to re-derive.

### 2.2 Tamarisk detection — **established, and phenology is the known discriminator**

| Study | Sensor / method | Result |
|---|---|---|
| [Mapping invasive *Tamarix* genotypes with Sentinel-2](https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/) | Sentinel-2 + Random Forest | **87.8% OA** (κ 0.85); SVM 86.3% |
| [Tamarisk on the Colorado River](https://doi.org/10.3390/rs1030318) (Hyperion / TM / QuickBird) | Multi-sensor comparison | **High-res (QuickBird 2.5 m) beat both Landsat TM (30 m) and hyperspectral Hyperion (30 m)** |
| [Phenological trajectory for saltcedar detection](https://diaorssilab.web.illinois.edu/wp-content/uploads/2023/11/Incorporating-plant-phenological-trajectory-in-exotic-saltcedar-detection-with-monthly-time-series-of-Landsat-imagery.pdf) | Monthly Landsat time series (MSAC) | Phenology-guided composite **beats any single scene**; **leaf senescence is the most discriminating stage** |
| [Single-scene vs time-series tamarisk mapping](https://www.researchgate.net/publication/26850021) | Landsat | Time-series > single-scene |
| Maximum-likelihood / NDVI, Colorado River | Landsat | 80–91% OA |

> **Honest consequence:** "Tamarix is separable from native riparian using multi-temporal
> optical imagery" is a **settled question**. We are not proving it. We are *operationalising*
> it. Two facts we must build on, not rediscover:
> 1. **Phenology — specifically late-season senescence — is the discriminator.** Tamarix holds
>    green later than cottonwood/willow.
> 2. **10 m is marginal for narrow corridors.** QuickBird at 2.5 m outperformed 30 m sensors.
>    Sentinel-2 at 10 m will suffer mixed pixels in narrow reaches (§7).

**This directly indicts our current OlmoEarth harness.** `delineation/olmoearth.py` **mean-pools
encoder tokens over the time axis**, which destroys exactly the senescence signal the literature
identifies as *the* discriminator. It is not a coincidence that the run underperformed. See #9.

### 2.3 Invasive labels — **already collected, and they are a gift**

**CSU/NREL invasive species occurrence dataset**, 2018 (*Data* journal) —
[project page](https://www.nrel.colostate.edu/improved-rip-maps-crb/)

- **3,000+ tamarisk and Russian-olive occurrence *and absence* locations** across AZ, CA, CO,
  NV, NM, UT ("select tributaries").
- Explicitly a **point occurrence dataset**, not a wall-to-wall map. CSU state that these are
  *"complementary products rather than a single integrated map of invasive versus native
  species."*

> **This solves our biggest label problem.** NMRipMap's `IC` class is *"Lowland **Introduced**
> Riparian Woodland and Scrub"* — it conflates **Tamarix and Russian olive** and cannot separate
> them (§5). These occurrence points can.

### 2.4 EO foundation models — applied to adjacent tasks, not to this one

- **OlmoEarth** (Ai2): the [`mangrove`](https://github.com/allenai/olmoearth_projects) project
  fine-tunes `OLMOEARTH_V1_BASE` on **12 monthly Sentinel-2 mosaics** → **97.6% accuracy**.
  Near-exact structural analog of our task.
- [Dargana / EarthPT](https://arxiv.org/pdf/2504.17321) — fine-tuning an EO foundation model for
  dynamic tree-canopy mapping.
- [Wetland mapping from sparse annotations with SITS + temporal-aware SAM](https://arxiv.org/pdf/2601.11400)
  — foundation model + **sparse/weak labels**, the closest methodological precedent to us.

No published work applies an EO foundation model to **riparian native-vs-invasive** mapping.

---

## 3. The actual gap — what is genuinely new

Given §2, the contribution is **not** "map riparian vegetation" and **not** "detect tamarisk."
Both are done. The gap is precise:

> **Nobody has produced a wall-to-wall, time-series, native-vs-invasive riparian *cover and
> change* product at reach scale for the basin.** CO-RIP gives extent (no species). The CSU
> occurrence dataset gives species (no map). They were never joined.

Our contribution, stated honestly:

| # | Contribution | Why it is not duplication |
|---|---|---|
| 1 | **Native-vs-invasive cover + change, wall-to-wall, per reach** | CO-RIP = extent only; CSU = points only; explicitly "complementary products," never integrated |
| 2 | **Weak labels harvested from existing authoritative GIS** (NMRipMap `L2` classes, CO-RIP raster, CSU points) with **confidence weighting** | The tamarisk literature depends on hand-digitised / field / UAV labels — the cost bottleneck. We mine labels that already exist. See the label ADR. |
| 3 | **EO foundation model fine-tune** (OlmoEarth, 12-month S2), transferring the `mangrove` recipe | Not attempted for riparian invasives; and the phenology literature says a temporal model is exactly right for this task |
| 4 | **Decision layer** — reach-scale alerts with *explanations* ("tamarix % of cover rose 11 pts in 5 yr") | The existing products are maps. Managers act on reaches, not pixels. |

If (1)–(4) fail to hold up, the honest fallback is: *we reproduced CO-RIP with better sensors.*
That must be said out loud rather than dressed up.

---

## 4. Class schema (phased)

Phased because **label supply, not model capacity, is the binding constraint.**

**Phase 1 — extent + confusion classes** *(implemented: `riparian/labels/nmripmap.py`)*
```
1 riparian_vegetation
2 water
3 agriculture_or_irrigated_pasture   <- THE confusion class in this basin
4 other
```
Agriculture gets its own class because irrigated pasture is spectrally near-identical to riparian
in the growing season — it is what defeated the weak labels (~0.00 F1 on the Animas ag valley),
and NMRipMap shows **299 agriculture polygons inside the Animas corridor alone**.

**Phase 2 — the product target** *(this spec)*
```
1 tamarix_or_introduced_woody     <- NMRipMap IC; split by CSU points where available
2 native_woody_riparian           <- NMRipMap IA/IB/IE/IIA/IIB
3 riparian_herbaceous_wetland     <- NMRipMap IIIA/IIIB
4 water                           <- NMRipMap IVB
5 agriculture                     <- NMRipMap IVD
6 other                           <- uplands, bare, developed, roads
```

**Phase 3 — species-level (`tamarix` vs `russian_olive` vs `willow_cottonwood`) — CUT for now.**
See §6.

---

## 5. Labels

| Source | Gives us | Confidence | Limitation |
|---|---|---|---|
| **NMRipMap** `L2_Code` (NM Natural Heritage) | `IC` = introduced woody riparian (**332 polygons on the Animas alone**); IA/IB/IE/IIA/IIB = native woody; IVB water; IVD agriculture | 0.85–0.95 | **NM only.** `IC` conflates Tamarix **and** Russian olive. |
| **CO-RIP** raster + valley bottoms | Riparian presence/absence, Colorado side; valley-bottom mask | 0.75 (κ 0.42–0.90 by ecoregion) | No species. Landsat-era. |
| **CSU/NREL occurrence points** | **Tamarisk vs Russian olive presence AND absence** (3,000+) | 0.90 | Points, "select tributaries" — coverage of the San Juan must be verified. |
| **NAIP** (manually digitised) | High-confidence validation polygons | 0.95 | Expensive; use for QA only, not bulk training. |

**Rule:** no source is ground truth. All are weak labels with a confidence. See the label ADR.

---

## 6. What we are cutting, and why

| Cut | Why |
|---|---|
| **Phase-3 / Level-4 species schema** (tamarix vs Russian olive vs willow vs cottonwood) | Label supply cannot carry it. NMRipMap's `IC` cannot separate the two introduced species; CSU points can, but only where they exist. The literature that achieves species-level separation ([Tamarix genotypes, S2](https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/)) uses field-collected labels we do not have. Attempting it now produces a confident, wrong map. |
| **Always-on GPU inference endpoint** | Riparian monitoring is **annual/seasonal batch**, not real-time. An idle GPU is pure cost. See the hosting ADR. |
| **Hyperspectral / UAV acquisition** | The [Colorado River comparison](https://doi.org/10.3390/rs1030318) found hyperspectral Hyperion at 30 m *lost* to QuickBird multispectral at 2.5 m — resolution mattered more than spectral depth. Neither is affordable basin-wide. Sentinel-2 + NAIP QA is the pragmatic pairing. |
| **"Rules-first MVP before any ML"** *(proposed, then dropped)* | We are past it. HAND, spatial CV, the reach product and the indices already exist. The blocker was never the rules — **it was the labels**, and that is now fixed (`riparian/labels/`). Rebuilding a rules MVP would itself be the duplication we are trying to avoid. |
| **Re-deriving riparian extent from scratch** | CO-RIP already did it basin-wide (§2.1). Use it as a label/baseline; do not re-derive it and call it new. |

---

## 7. Method, and the trade-offs we are accepting

**Input.** 12 monthly Sentinel-2 L2A mosaics (a full phenological year), matching both the
OlmoEarth `mangrove` recipe and the saltcedar phenology literature. **The late-season
(senescence) window carries the signal** — Tamarix stays green after natives brown — so the model
must see the whole year, and must not average it away.

**Model.** Fine-tune `OLMOEARTH_V1_BASE` with a segmentation decoder (`FreezeUnfreeze`, unfreeze
at epoch 20 / 10× LR), per the `mangrove` config. Scaffold: `olmoearth_run_data/riparian_extent/`.

**Baseline to beat.** Not "nothing" — **CO-RIP (κ 0.80)** and the published tamarisk RF/S2 result
(**87.8% OA**). If we cannot beat those, we have not contributed.

**Validation.** Spatial (hashed-grid) splits, never random — Sentinel-2 pixels are strongly
autocorrelated. Plus NAIP-digitised polygons as an independent check.

### Trade-offs accepted

| Trade-off | Consequence | Mitigation |
|---|---|---|
| **Sentinel-2 at 10 m** in corridors often < 30 m wide | Mixed pixels; the literature shows 2.5 m materially outperforms 30 m | Report per-reach **confidence**; flag narrow reaches for NAIP review rather than asserting a class |
| **`IC` conflates Tamarix + Russian olive** | Cannot claim species-level tamarisk from NMRipMap alone | Report as `introduced_woody` until CSU points are joined; never label a map "Tamarix" that is actually "introduced" |
| **Weak GIS labels are noisier than field data** | Ceiling on achievable accuracy | Confidence weighting; NAIP QA; report the label provenance with every metric |
| **NM has NMRipMap; CO does not** | Asymmetric label quality across the basin | CO-RIP + CNHP for the Colorado side; **report NM and CO accuracy separately** — never one blended number |

---

## 8. Outputs

**Raster (per year):** `tamarix_probability.tif`, `native_riparian_probability.tif`,
`riparian_class.tif`, `confidence.tif`

**Reach table (the product):**
```
reach_id, year,
tamarix_acres, native_riparian_acres, total_riparian_acres,
tamarix_pct_of_riparian,
tamarix_change_1yr, tamarix_change_5yr,
native_change_1yr, native_change_5yr,
dominant_change_type, confidence, review_priority
```

**The alert that justifies the project:**
> `SanJuan-117`: total riparian cover **+3%**, but Tamarix went **30% → 41%** of cover.
> Native cover **fell**. Flag: `invasive_expansion` — not recovery.

---

## 9. Open questions

1. Do the CSU/NREL occurrence points actually cover the **San Juan**? ("select tributaries" is
   unverified — this determines whether Phase-3 species split is reachable at all.)
2. Does CO-RIP's Landsat-era vegetation raster still agree with current Sentinel-2 observations,
   or has the corridor moved enough that it is a *historical* label?
3. ~~Where has biocontrol been released in the basin?~~ **ANSWERED (2026-07-11) — and it is bad
   news.** The northern tamarisk beetle was **released directly on the Dolores, Colorado and San
   Juan Rivers in 2004–2007**, and by 2014 was present on **virtually all Upper Basin river
   systems and tributaries**. There is therefore **no un-confounded control area inside our AOI**.
   Defoliated Tamarix browns *early*, inverting the late-senescence discriminator the entire
   tamarisk-mapping literature relies on. Consequences we must design for:
   - A phenology classifier may **systematically miss defoliated stands**.
   - **A greenness decline in a Tamarix reach is NOT recovery** — it may be biocontrol working.
     Reporting it as restoration success would be the exact error this spec exists to prevent.
   - Defoliation is **episodic and non-stationary** (multiple events per season, varying by year),
     so a model trained on year *X* may not transfer to year *Y*.
   - **Model defoliation as a state**, not as Tamarix absence. Prefer the **early-season leaf-out**
     window, which biocontrol perturbs less than senescence.
   - Key reference, now in the RAG corpus: USGS **OFR 2018-1070**, which documents plant phenology
     and beetle abundance **on the San Juan itself**. https://pubs.usgs.gov/of/2018/1070/ofr20181070.pdf

---

## 10. References

- Woodward et al. (2018). *CO-RIP: A Riparian Vegetation and Corridor Extent Dataset for Colorado
  River Basin Streams and Rivers.* ISPRS IJGI 7(10):397. https://www.mdpi.com/2220-9964/7/10/397 ·
  data: https://doi.org/10.5061/dryad.3g55sv8
- CSU/NREL. *Improved maps and invasive species data for the Colorado River Basin* (invasive
  occurrence dataset, 2018). https://www.nrel.colostate.edu/improved-rip-maps-crb/
- *A rapid and accurate method of mapping invasive Tamarix genotypes using Sentinel-2 images.*
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/
- *Remote Sensing and Mapping of Tamarisk along the Colorado River* (Hyperion / TM / QuickBird).
  https://doi.org/10.3390/rs1030318
- Diao & Wang. *Incorporating plant phenological trajectory in exotic saltcedar detection with
  monthly time series of Landsat imagery.*
- Ai2 OlmoEarth — `olmoearth_projects` (`mangrove`): https://github.com/allenai/olmoearth_projects
- Dargana: fine-tuning EarthPT for tree-canopy mapping. https://arxiv.org/pdf/2504.17321
- Wetland mapping from sparse annotations with SITS + temporal-aware SAM.
  https://arxiv.org/pdf/2601.11400
- NMRipMap v2.0 Plus — NM Natural Heritage (NMEDB ArcGIS MapServer, GRSJ layers).
