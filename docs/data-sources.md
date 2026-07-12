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
