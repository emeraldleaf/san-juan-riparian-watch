# Literature review — riparian mapping, Tamarix, and Earth-observation foundation models

**San Juan Riparian Watch** · Compiled 2026-07-11

> **Purpose.** Establish what has already been done, so this project builds on prior work rather
> than re-deriving it — and so every claim of novelty is defensible. Two of our existing
> components substantially reproduce published work; that is stated plainly in §2 and §3.
>
> Companion documents: the Stage-2 spec (`docs/specs/2026-07-11-stage2-invasives-tamarix.md`),
> the label ADR, and the hosting ADR.

---

## 1. Scope

Four questions:

1. Has basin-scale riparian extent already been mapped for the San Juan? — **Yes.** (§2)
2. Is Tamarix separable from native riparian by remote sensing? — **Yes, and the mechanism is
   known.** (§3)
3. Does anything invalidate that mechanism in *our* basin? — **Yes: biocontrol defoliation.** (§4)
4. Has anyone applied an EO foundation model to this task? — **No.** (§6)

---

## 2. Basin-scale riparian extent mapping — already solved

### 2.1 CO-RIP (the one that matters)

**Woodward, B. et al. (2018).** *CO-RIP: A Riparian Vegetation and Corridor Extent Dataset for
Colorado River Basin Streams and Rivers.* **ISPRS Int. J. Geo-Inf.** 7(10):397.
[Paper](https://www.mdpi.com/2220-9964/7/10/397) · [Data (Dryad)](https://doi.org/10.5061/dryad.3g55sv8)

- **Coverage:** the entire Colorado River Basin — **637,000 km², 7 states — including the San Juan.**
- **Method:** valley-bottom delineation → **Random Forest on Landsat spectral data**, per ecoregion.
- **Accuracy:** median **κ = 0.80**, range **0.42–0.90** across 12 ecoregions.
- **Products:** riparian vegetation raster (`0` absence / `100` presence) + valley-bottom polygons.

> **Direct consequence for this project.** Our Stage-1 RF baseline is *the same method class*:
> our HAND valley-bottom envelope ≈ their valley-bottom delineation; our RF on multitemporal
> spectral features ≈ their RF on Landsat. **Building an RF riparian classifier for this basin is
> not a contribution.** CO-RIP is a *baseline to beat* and a *label source to exploit*.
> The wide κ range (0.42–0.90) is itself informative: performance is ecoregion-dependent, so a
> single blended accuracy number for the basin is misleading — ours must be reported per region.

### 2.2 Reference vegetation maps used as labels

- **NMRipMap v2.0 Plus** (New Mexico Natural Heritage / NMEDB). Hierarchically classified riparian
  mapping units (`L1`/`L2`/`L3`, plus NVC macrogroup/group/alliance, SWAP habitat, and quantitative
  cover: `Woody_Cov`, `Tot_Tree_Cov`, `Wdy_Ht_Mn`). **New Mexico only.**
  Critically, `L2 = IC` — *"Lowland **Introduced** Riparian Woodland and Scrub"* — is an
  authoritative **introduced-woody (Tamarix / Russian olive)** class.
- **NWI** (USFWS National Wetlands Inventory) — wetland, not riparian; useful for the `water` and
  wetland classes, not as a riparian target.
- **CNHP Wetlands Mapper** (Colorado Natural Heritage Program) — Colorado-side wetland/riparian.
- **NLCD / LANDFIRE** — coarse (30 m) context and confusion classes (`pasture/hay`,
  `cultivated_crops`), not riparian targets.

---

## 3. Tamarix / saltcedar remote sensing — established, and phenology is the mechanism

| Study | Sensor / method | Result |
|---|---|---|
| [Mapping invasive *Tamarix* genotypes with Sentinel-2](https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/) | Sentinel-2 + Random Forest | **87.8% OA** (κ 0.85); SVM 86.3% (κ 0.83) |
| [Tamarisk along the Colorado River](https://doi.org/10.3390/rs1030318) | Hyperion (30 m, hyperspectral) vs Landsat TM (30 m) vs QuickBird (2.5 m) | **QuickBird at 2.5 m beat both 30 m sensors** — spatial resolution mattered more than spectral depth |
| [Phenological trajectory for saltcedar detection](https://diaorssilab.web.illinois.edu/wp-content/uploads/2023/11/Incorporating-plant-phenological-trajectory-in-exotic-saltcedar-detection-with-monthly-time-series-of-Landsat-imagery.pdf) (Diao & Wang) | Monthly Landsat time series (MSAC) | Phenology-guided composite **beats any single scene**; **leaf senescence is the most discriminating stage** |
| [Single-scene vs time-series tamarisk mapping](https://www.researchgate.net/publication/26850021) | Landsat | Time-series > single-scene |
| Maximum-likelihood / NDVI, Colorado River | Landsat | 80–91% OA |

**Mechanism.** *Tamarix* has a **longer growing season than native cottonwood/willow** — it leafs
out earlier and, decisively, **holds green foliage later into the autumn**. Late-season senescence
contrast is therefore the primary spectral separability window, and this is why *time series beat
single scenes* consistently across the literature.

**Three implications we must design around:**

1. **A model must see the full phenological year** — and must not average it away.
   > This directly indicts our current OlmoEarth harness (`delineation/olmoearth.py`), which
   > **mean-pools encoder tokens over the time axis**, destroying precisely the senescence signal
   > the literature identifies as *the* discriminator. See issue #9.
2. **10 m is marginal for narrow corridors.** If 2.5 m QuickBird outperformed 30 m sensors, then
   Sentinel-2 at 10 m will suffer mixed pixels wherever the corridor is narrower than ~30 m.
   Confidence must be reported, not hidden.
3. **The published bar is ~87–91% OA.** "We detected tamarisk" is not a result. Beating or matching
   that *at basin scale with weak labels* would be.

---

## 4. The biocontrol confound — the most important finding in this review

**CONFIRMED for our exact AOI — this is not a hypothetical risk, it is the ground condition.**

- The northern tamarisk beetle (*Diorhabda carinulata*) was released in 2001 (CA, CO, UT, TX).
- **Releases were made directly on the Dolores, Colorado, and *San Juan* Rivers, 2004–2007.**
- **By 2014 the beetle was present on virtually all river systems and tributaries in the Upper
  Basin** — i.e. across the whole San Juan network.
- USGS **OFR 2018-1070** — *Population dynamics of the northern tamarisk beetle in the Colorado
  River Basin* ([PDF](https://pubs.usgs.gov/of/2018/1070/ofr20181070.pdf)) — documents **plant
  phenology and beetle abundance/movement specifically along the Dolores and San Juan Rivers.**
  It is the single most important reference for this project's Tamarix work, and is now in the
  doc-intelligence corpus.
- Expert-panel synthesis: [USGS 70168717](https://pubs.usgs.gov/publication/70168717).

Remote-sensing studies of the resulting defoliation:

- [Detection of tamarisk defoliation by the northern tamarisk beetle using multitemporal Landsat 5 TM](https://pubs.usgs.gov/publication/70040060) — USGS. Compared a **Disturbance Index** against
  **Random Forest**; RF detected smaller areas but with **higher accuracy** (784 ha in 2007 → 1,008 ha
  in 2010).
- [Remote sensing of tamarisk beetle impacts along 412 km of the Colorado River, Grand Canyon](https://pubs.usgs.gov/publication/70196440) — NDVI decline ratio > 1.5 between dates; local
  defoliation 1–86%.

### Why this is a hazard for us

The separability mechanism in §3 is *"Tamarix stays green after natives brown."*
**Beetle-defoliated Tamarix browns early — inverting the discriminator.**

Consequences:

- A phenology-based Tamarix classifier trained on **pre-beetle** or **non-defoliated** conditions
  may **systematically miss defoliated stands**, or misclassify them as senescing natives / stressed
  vegetation.
- Defoliation is **episodic and repeated** (multiple events per growing season, varying year to year),
  so the confound is **non-stationary**: a model trained on year *X* may not transfer to year *Y*.
- Conversely, a **greenness decline in a Tamarix stand is not necessarily good news** and is
  certainly not "restoration." It may be biocontrol working — or it may be native loss.

**Design responses (adopted into the Stage-2 spec):**
1. Treat **defoliation as its own state**, not as evidence of Tamarix absence.
2. **Never** interpret an NDVI/EVI decline in a known Tamarix reach as recovery without checking
   the defoliation hypothesis.
3. Where beetle presence is known, weight the **early-season (leaf-out)** phenology window, which
   biocontrol perturbs less than senescence.
4. Record beetle-release/defoliation geography as a covariate. **Answered:** releases were made
   *on the San Juan itself* (2004–2007) and the beetle saturated the Upper Basin by 2014 — so
   there is **no un-confounded control area within the AOI**. The covariate is not "where is the
   beetle" (everywhere) but **"where and when did defoliation actually occur"**, which USGS
   OFR 2018-1070 and the VI-decline detection methods (§4) can supply.
5. **The vintage of our labels now matters.** NMRipMap's `IC` (introduced woody) polygons were
   mapped over a period that overlaps the defoliation era. A stand mapped as Tamarix may since
   have been repeatedly defoliated — or died back. Label age must be carried as metadata, not
   assumed current.

---

## 5. Riparian condition, greenness and water use — the USGS/Nagler line of work

- **Nagler, P. et al. (2021).** *Riparian Area Changes in Greenness and Water Use on the Lower
  Colorado River in the USA from 2000 to 2020.* **Remote Sensing** 13(7):1332.
  [DOI](https://doi.org/10.3390/rs13071332) ·
  [USGS](https://www.usgs.gov/publications/riparian-area-changes-greenness-and-water-use-lower-colorado-river-usa-2000-2020)
- **Riparian Ecosystem Data Explorer** (USGS + University of Arizona) — interactive 20-year
  time-series of **EVI2** (greenness proxy), **daily ET**, **annualized ET**, and the **Phenology
  Assessment Metric (PAM-ET)**, built explicitly to monitor **tamarisk-beetle defoliation events**.
  [RiversEdge West](https://riversedgewest.org/documents/riparian-ecosystem-data-explorer-monitoring-lower-colorado-river-integrated-and-dynamic)

**Key finding:** riparian health and water use on the Lower Colorado **have declined since 2000**,
a loss attributed **in part to biocontrol**.

**Scope caveat (important):** this work covers the **Lower** Colorado (Hoover Dam → delta). It is
**not a San Juan data source.** Its value to us is **methodological**: EVI2 as a greenness proxy,
PAM-ET as an annualized phenology/water-use metric, and the demonstration that defoliation is
legible in VI/ET time series. We adopt the metrics, not the data.

---

## 6. Earth-observation foundation models

- **OlmoEarth** (Ai2). Open EO foundation-model family (Nano/Tiny/Small/Base). The published
  [`mangrove`](https://github.com/allenai/olmoearth_projects) project fine-tunes `OLMOEARTH_V1_BASE`
  on **12 monthly Sentinel-2 mosaics** with a segmentation decoder (`FreezeUnfreeze`: encoder
  unfrozen at epoch 20 at 10× LR) → **97.6% overall accuracy**, validated against **Global Mangrove
  Watch**. **v1.1** merges S2 bands into single tokens for ~**3× less compute**; **v1.2** adds RoPE.
  Structurally, mangrove mapping is a near-exact analog of riparian delineation: *woody vegetation
  near water, from an S2 time series, validated against an authoritative reference map.*
- **Dargana / EarthPT** — [fine-tuning an EO foundation model for dynamic tree-canopy mapping](https://arxiv.org/pdf/2504.17321).
- **Wetland mapping from sparse annotations with SITS + a temporal-aware SAM** —
  [arXiv](https://arxiv.org/pdf/2601.11400). The closest methodological precedent to our approach:
  a temporal foundation model supervised by **sparse/weak labels**.

**Gap:** no published work applies an EO foundation model to **riparian native-vs-invasive** mapping.

---

## 7. Weak / sparse supervision from existing GIS

The tamarisk and riparian literature is overwhelmingly supervised by **hand-digitised, field, or UAV
labels** — the cost bottleneck that keeps these studies at site or reach scale. The alternative,
now viable, is to **mine labels from already-published authoritative GIS** and carry a confidence per
source (NMRipMap classes, CO-RIP raster, CSU occurrence points), rather than annotate from scratch.

Precedent: the wetland/SAM work above supervises a temporal foundation model from sparse annotations.
Our variant is that the weak labels are **existing authoritative products**.

See ADR `2026-07-11-confidence-weighted-label-crosswalk.md`.

---

## 8. Synthesis — what is solved, what is open, what we contribute

**Solved (do not re-derive):**
- Basin-scale riparian **extent** — CO-RIP, κ 0.80, covers the San Juan (§2.1).
- Tamarix **detectability** from multi-temporal optical imagery — 87–91% OA, phenology-driven (§3).
- Defoliation **detectability** in VI time series — USGS Landsat work (§4).

**Open (the real gaps):**
1. **No wall-to-wall, time-series, native-vs-invasive riparian *cover + change* product.** CO-RIP gives
   extent without species; the CSU/NREL 2018 dataset gives **3,000+ tamarisk/Russian-olive occurrence
   and absence points** but no map — CSU describe these as *"complementary products rather than a
   single integrated map of invasive versus native species."*
   [CSU/NREL](https://www.nrel.colostate.edu/improved-rip-maps-crb/) **They were never joined.**
2. **No EO foundation model applied to riparian invasives** (§6).
3. **The biocontrol confound is not handled** in any operational riparian classifier we found (§4) —
   despite the beetle being established across the upper basin, i.e. *our* basin.
4. **Labels remain the bottleneck** — the literature annotates; nobody systematically mines the
   existing authoritative GIS as confidence-weighted weak labels (§7).

**Our contribution, stated so it can be falsified:**

| # | Claim | Falsified if… |
|---|---|---|
| 1 | Native-vs-invasive riparian **cover + change**, wall-to-wall, at reach scale | someone shows an existing integrated product for the basin |
| 2 | Weak labels **mined from existing authoritative GIS** with confidence weighting | hand-annotation proves necessary for usable accuracy |
| 3 | **EO foundation-model** fine-tune (OlmoEarth, 12-month S2) for this task | a properly fine-tuned Base fails to beat CO-RIP (κ 0.80) / the S2-RF bar (87.8%) |
| 4 | **Biocontrol-aware** phenology — defoliation as a state, not as absence | defoliation proves spectrally unimportant in this basin |
| 5 | **Decision layer** — reach-scale alerts with explanations | managers find pixel maps sufficient |

If (1)–(5) fail, the honest fallback is: *we reproduced CO-RIP with better sensors.* That sentence
must stay in the repo.

---

## 9. References

**Riparian mapping / datasets**
1. Woodward, B. et al. (2018). *CO-RIP: A Riparian Vegetation and Corridor Extent Dataset for
   Colorado River Basin Streams and Rivers.* ISPRS IJGI 7(10):397.
   https://www.mdpi.com/2220-9964/7/10/397 · https://doi.org/10.5061/dryad.3g55sv8
2. CSU/NREL (2018). *Improved maps and invasive species data for the Colorado River Basin* —
   tamarisk & Russian-olive occurrence/absence dataset (3,000+ locations).
   https://www.nrel.colostate.edu/improved-rip-maps-crb/
3. NMRipMap v2.0 Plus — New Mexico Natural Heritage / NMEDB (GRSJ layers; `L1`/`L2`/`L3` classes).
4. USFWS National Wetlands Inventory. · Colorado Natural Heritage Program Wetlands Mapper.

**Tamarix remote sensing**
5. *A rapid and accurate method of mapping invasive Tamarix genotypes using Sentinel-2 images.*
   https://pmc.ncbi.nlm.nih.gov/articles/PMC10117385/
6. *Remote Sensing and Mapping of Tamarisk along the Colorado River, USA: Hyperion, Thematic Mapper
   and QuickBird.* Remote Sensing 1(3):318. https://doi.org/10.3390/rs1030318
7. Diao, C. & Wang, L. *Incorporating plant phenological trajectory in exotic saltcedar detection
   with monthly time series of Landsat imagery.*
8. *Mapping Invasive Tamarisk: A Comparison of Single-Scene and Time-Series Analyses of Remotely
   Sensed Data.* https://www.researchgate.net/publication/26850021

**Biocontrol / defoliation**
9. *Detection of tamarisk defoliation by the northern tamarisk beetle based on multitemporal
   Landsat 5 TM imagery.* USGS. https://pubs.usgs.gov/publication/70040060
10. *Remote sensing of tamarisk beetle (Diorhabda carinulata) impacts along 412 km of the Colorado
    River in the Grand Canyon, Arizona.* USGS. https://pubs.usgs.gov/publication/70196440

**Riparian condition / ET**
11. Nagler, P. et al. (2021). *Riparian Area Changes in Greenness and Water Use on the Lower
    Colorado River, 2000–2020.* Remote Sensing 13(7):1332. https://doi.org/10.3390/rs13071332
12. *A Riparian Ecosystem Data Explorer for Monitoring the Lower Colorado River* (USGS / Univ. of
    Arizona). https://riversedgewest.org/documents/riparian-ecosystem-data-explorer-monitoring-lower-colorado-river-integrated-and-dynamic

**Foundation models / weak supervision**
13. Ai2 OlmoEarth — models, `olmoearth_projects` (incl. `mangrove`), v1.1/v1.2.
    https://github.com/allenai/olmoearth_projects · https://allenai.org/blog/olmoearth-v1-1
14. *Dargana: fine-tuning EarthPT for dynamic tree canopy mapping from space.*
    https://arxiv.org/pdf/2504.17321
15. *Wetland mapping from sparse annotations with satellite image time series and a temporal-aware
    segment anything model.* https://arxiv.org/pdf/2601.11400

**Basin context**
16. SJRIP / Bassett (2015). *San Juan River Historical Ecology Assessment: Changes in Channel
    Characteristics and Riparian Vegetation.* (Already in the doc-intelligence corpus.)
