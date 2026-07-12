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
`100` presence) + valley-bottom polygons, **whole basin, per-ecoregion**.

NMRipMap is **New Mexico only**, which is why the Turkey Creek (CO) tile has no reference map and
stays on weak labels. **CO-RIP covers it.**

🔴 **Its imagery epoch is not stated on the Dryad page.** Our own vintage rule makes that
**blocking**: read the bundled README / the paper and record the year *before* fitting anything
against it.
