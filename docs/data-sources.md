# Data sources

All free, no API key. Study area: **San Juan Basin, HUC8 `14080101`**. See CLAUDE.md.


### Labels / reference (what the models are trained and scored against)
- **NMRipMap v2.0 Plus** — *the* label source for delineation AND invasives:
  https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/NM_RipMap_2_0_Plus_All_Levels/MapServer/13
  - **Classified**, not a plain mask: filter on `L2_Code`. `IC` = introduced woody riparian
    (**free tamarisk / Russian-olive ground truth**). Rasterizing *every* polygon as riparian made
    ~45% of positive labels wrong. Use `riparian/labels/nmripmap.py`, never a raw fetch.
  - 🔴 **Label vintage = 2020** (photo-interpreted from NAIP 2020). **Fit on 2020 imagery; predict
    any year.** New Mexico only — CO tiles have no NMRipMap.
- **CO-RIP** (Woodward et al. 2018) — basin-wide riparian extent, κ 0.80. A *baseline to beat and a
  label source for Colorado*, not something to re-derive: https://doi.org/10.5061/dryad.3g55sv8
- **CSU/NREL invasive occurrence points** (2018) — 3,000+ tamarisk *and* Russian-olive occurrence +
  absence points. The only source that can **split** the two species NMRipMap's `IC` conflates:
  https://www.nrel.colostate.edu/improved-rip-maps-crb/

### Imagery (Planetary Computer STAC — https://planetarycomputer.microsoft.com/api/stac/v1)
- **Sentinel-2 L2A** (10 m, from 2015-10) · **Sentinel-1 RTC** · **3DEP LiDAR**
- **Landsat** (30 m, from **1984**) — the only sensor reaching the **pre-beetle era** (*Diorhabda*
  released 2004–07), and the one CO-RIP used. **NAIP** — what NMRipMap was interpreted from.
  OlmoEarth ingests all three natively (`Modality` enum).

### Ancillary
- NHDPlus V2.1: https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/NHDPlusV21/FeatureServer
- Colorado Parcels: https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0
- USDA Watersheds: https://apps.fs.usda.gov/ArcX/rest/services/EDW/EDW_Watersheds_01/MapServer
- NWI Wetlands: https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0
- SSURGO Soils: https://SDMDataAccess.sc.egov.usda.gov/ (spatial WFS + tabular REST)
- LANDFIRE EVT/EVH LF250: https://lfps.usgs.gov/arcgis/rest/services/Landfire_LF250/
- MRLC NLCD: https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/ows —
  wired via EROS ImageServer with the MRLC GeoServer WMS as **fallback** (`FallbackRasterSource`).
- **RAG corpus** (doc-intelligence): 25 seed sources in `docintel/corpus/seed_sources.yaml`
  (watershed plans, SJRIP reports, riparian/invasives science). Not fetched by the ETL.

## Label sources unlocked by the prior-art audits (2026-07-12)

The audits surfaced **usable data**, not just claims. See `docs/audits/`.

### CSU/NREL field points — `TabletData_2017.csv` ⭐ the beetle labels
[Vorster et al. 2018, *Data* 3(4):42](https://doi.org/10.3390/data3040042) ·
**[direct CSV](https://mountainscholar.org/bitstreams/133b91bb-f416-4a18-aac8-1062d7d884dd/download)**
(326 KB, CSU Research Data Terms of Use) · **3,491 records, collected 2017**

Columns: `OBJECTID, PlotID, Species, GlobalID, x, y, TripName`. ~7 m radius plots — a good match to
**Sentinel-2's 10 m**, and far better than Landsat 30 m (which is exactly what CSU said defeated them).

It solves three problems NMRipMap cannot:

| Class | n | Why it matters |
|---|---|---|
| `tamarisk` | 1,374 | live tamarisk |
| **`red tam`** | **283** | **red foliage from beetle attack — DEFOLIATION LABELS** |
| **`live dead tam mix`** | **193** | partial defoliation |
| `dead tam` | 71 | dead |
| `Russian olive` / `Russian Olive` | **191** | **separates the species NMRipMap's `IC` conflates** |
| cottonwood, willow, mesquite, box elder … | ~630 | native negatives |
| water, bare ground, ag, road, `absent_point` | ~530 | **real absences** (we currently use random background) |

**547 beetle-affected tamarisk points.** Our "defoliation as a state, not absence" claim had **no
labels at all** before this.

🔴 **Two constraints, verified by downloading and counting — do not skip these:**
1. **Only 167 points fall inside the San Juan basin** — 49 Russian olive, 47 tamarisk, 39 native
   riparian woody, 13 agriculture, 10 absence. Enough to **split the species locally** and to
   validate — **not** enough to train alone. *(Counted by `riparian/labels/csu_points.py`, which
   supersedes an earlier rough bbox estimate of ~148.)*
2. 🔴 **Zero `red tam` (defoliated) points in our AOI** — all 283 are Arizona / Escalante. The AOI has
   only **4 `mixed`** beetle-affected points. **Defoliation must be learned basin-wide and
   transferred, or the AOI widened.** We cannot locally validate the beetle signal from this dataset,
   and that is the single most important scoping fact for Stage 2.
3. 🐛 **The `Virgin_River` trip has x/y TRANSPOSED** in the source file (`x` holds 35.8–38.6, `y` holds
   −114…−108). A naive loader puts 119 points in the wrong hemisphere. Also normalize the casing —
   `Russian olive` / `Russian Olive` / `tamarisk` / `Tamarisk` are all present. Crosswalk it like
   NMRipMap; never trust a raw `Species` string.

**Label vintage: 2017** → fit against **2017** imagery. See CLAUDE.md.

### CO-RIP — the Colorado label source we lack
[Dryad, 1.25 GB](https://doi.org/10.5061/dryad.3g55sv8) — riparian vegetation raster (`0` absence /
`100` presence) + valley-bottom polygons, **whole basin, per EPA Level III ecoregion**, **30 m**.

NMRipMap is **New Mexico only**, which is why the Turkey Creek (CO) tile has no reference map and
stays on weak labels. **CO-RIP covers it.** Loader: `riparian/labels/corip.py`.

✅ **Vintage resolved: 2006 and 2016.** The Dryad page never states it and the README sits behind an
auth token, so it came from the source team's own report (Evangelista et al. 2018, §Goal 1):
*"We used **Landsat** cloud free growing season composites … random forest models of riparian
vegetation for each ecoregion in **2006 and 2016** … at a **30 m** resolution."*
**Fit against imagery from whichever year you load.**

🔴 **CO-RIP is WEAKEST exactly where we need it — and it OVER-PREDICTS there.** In the authors' words:
*"OOB errors ranging from **2% – 35%, depending on the ecoregion** … ecoregions further north and
encompassing **mountainous regions had lower accuracy**"* and *"our map may likely **over predict
riparian vegetation in high elevation environments**."*

**Turkey Creek — the very tile we want CO-RIP for — is northern, mountainous, high-elevation Southern
Rockies.** So CO-RIP is **not ground truth in Colorado**: it is a confidence-weighted weak label
(`confidence 0.55` for Southern Rockies vs `0.95` arid lowland), per the
[confidence-weighted label ADR](decisions/2026-07-11-confidence-weighted-label-crosswalk.md). An
over-predicting label is worse than a missing one — it teaches the model that **upland is riparian**,
which is precisely the failure the NMRipMap crosswalk exists to prevent.

Also, for Stage 3: the authors warn their own change product may show *"changes … due to **model
errors when comparing the two years**"* rather than real change.

**Download is manual** — Dryad blocks automated fetches (401/403). `corip.download_instructions()`
prints the steps rather than failing with a 403.

## The CSU/NREL GIS products — where they are, and what they actually cover

Found 2026-07-12 by chasing the prior-art audit into the repository the report names only as
"Colorado State University Library". It is **[Mountain Scholar](https://mountainscholar.org)**, the
same repository the field points came from, in a dedicated collection:
**"Research Data — Riparian Habitat and Invasive Species in the Colorado River Basin"**
(handle `10217/195562`). Eight products, all openly downloadable via the DSpace REST API.

| Product | File | Size | Usable as GIS? |
|---|---|---|---|
| **Tamarisk probability, 2016** | `2016_tam_prob_BufClip_mosaic_FULL2.tif` | **11 MB** | ✅ **GeoTIFF**, 30 m, float32, **p ∈ 0–1**, ESRI:102008 |
| **Valley bottoms (VBET), whole basin** | `VBETfiles.zip` | 1.3 GB | ✅ the "maximum riparian corridor extent" — what our HAND envelope re-derives |
| Riparian vegetation 2006 / 2016 / change | `RiparianVegtation_AtlasBook_FINAL.pdf` | 1.5 GB | ❌ **a PDF map-book**, not data |
| Tamarisk occurrence 2005–2007 | `Tam_2005_to_2007_...FinalMap.pdf` | 2.3 MB | ❌ PDF |
| Tamarisk occurrence 2015–2017 | `Tam_2015_to_2017_...FinalMap.pdf` | 1.5 MB | ❌ PDF |

### 🔴 The tamarisk probability raster does NOT cover the San Juan — measured, not assumed

Downloaded it and counted valid pixels. This is the headline fact:

| Region | Valid pixels | |
|---|---|---|
| **San Juan (entire HUC8)** | **0** | **NOT COVERED** |
| Escalante | 0 | not covered |
| **Dolores** | 36,114 | covered (mean p = 0.54) |
| **Green River** | 121,070 | covered |

Their report says *"**Select** tamarisk modeling results for 2016"*, and their case studies were
*tamarisk on the **Dolores*** and *Russian olive on the **San Juan***. **The word "select" is load-
bearing, and we have now verified it empirically instead of trusting it.**

**Consequences:**
- It **cannot** serve as weak labels or a benchmark **for our AOI**. There is nothing there.
- It **empirically confirms our novelty claim**: the incumbent's species product is genuinely *not*
  wall-to-wall, and **the San Juan is not in it**. That is now a measurement, not a reading of their
  abstract.
- It **is** usable on the **Dolores** — same Colorado Plateau ecoregion as our training pool, and one
  of the rivers *Diorhabda* was released on (2004–07). So it is a **method benchmark**: run our model
  on the Dolores and compare against the incumbent's own output, on ground they claim.
- **Vintage 2016** (Landsat 30 m) — fit against 2016 imagery, and inherit their own caveat that
  Landsat cannot resolve the tamarisk phenological signature.

### Fetching them

Dryad blocks automation; **Mountain Scholar does not**. Bitstreams download cleanly from
`https://api.mountainscholar.org/server/api/core/bitstreams/<uuid>/content` — e.g. the tamarisk
probability raster is `a61038aa-b918-4ca4-83ce-770a44f9a83b`.
