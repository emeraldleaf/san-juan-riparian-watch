# Licences — code vs. data are NOT the same here

**Two licences. Read both before publishing anything derived from this repo.**

| What | Licence |
|---|---|
| **Source code** (`python-etl/`, `RiparianPoc.*`, `frontend/`, `.claude/`, scripts) | **Apache-2.0** — see [`LICENSE`](LICENSE) |
| **Data products** — trained models, label layers, extent/invasive rasters, reach products, maps | **CC BY-SA 4.0** — *not our choice; see below* |

## Why the data products are CC BY-SA, and why that is not optional

This project trains on datasets published under **CC BY-SA 4.0**:

- **CSU/NREL field points** (Vorster et al. 2018) — the tamarisk/Russian-olive occurrence, absence and
  **defoliation-state** records our beetle-aware work depends on.
- **CSU/NREL valley bottoms (VBET)** and **tamarisk probability raster** (Evangelista et al. 2018).

**CC BY-SA's ShareAlike clause requires adapted material to carry the same licence.** A label layer, a
probability raster, or an invasive-cover map built from those inputs is adapted material. So:

- ✅ We **may** train on them — including commercially. Attribution is mandatory.
- ⚠️ We **must** release derived **data products** under **CC BY-SA 4.0**. We cannot relicense them
  more permissively, and must not imply we have.
- ⚖️ **Model weights are legally unsettled.** Whether trained weights are a derivative of their
  training data is genuinely contested. **We take the conservative position** and release any published
  weights under **CC BY-SA 4.0 with attribution.** For an open-science project this costs nothing, and
  claiming the question is settled would be dishonest.
- 🧩 **Code is unaffected.** A data licence does not reach code that merely reads the data. Hence
  Apache-2.0 (permissive, with an explicit patent grant — the sensible default for ML work).

**Plan for this. Do not discover it at publication.** The Stage-2 and Stage-3 outputs — the products
this project exists to make — are **CC BY-SA 4.0**.

## Attribution (required)

> **Vorster, A., Evangelista, P., West, A., et al. (2018).** *Tamarisk and Russian Olive Occurrence and
> Absence Dataset Collected in Select Tributaries of the Colorado River for 2017.* *Data* 3(4):42.
> CC BY-SA 4.0.
>
> **Evangelista, P., Young, N., Vorster, A., West, A., Hatcher, E., Woodward, B., Anderson, R., &
> Girma, R. (2018).** *Mapping Native and Non-Native Riparian Vegetation in the Colorado River
> Watershed.* CSU Natural Resource Ecology Laboratory / USGS / NASA DEVELOP. CC BY-SA 4.0.
> *(Source of the VBET valley bottoms and the 2016 tamarisk probability raster.)*
>
> **Woodward, B., Evangelista, P., Vorster, A., et al. (2018).** *CO-RIP: A Riparian Vegetation and
> Corridor Extent Dataset for Colorado River Basin Streams and Rivers.* *ISPRS Int. J. Geo-Inf.*
> 7(10):397.
>
> **Muldavin, E., Milford, E., Triepke, J., et al. (2023).** *New Mexico Riparian Habitat Map
> (NMRipMap) Version 2.0 Plus.* New Mexico Natural Heritage Program, University of New Mexico.

Imagery: **Sentinel-2 / Sentinel-1** (ESA, Copernicus), **Landsat / 3DEP** (USGS), **NAIP** (USDA),
accessed via Microsoft Planetary Computer.

Details and the per-dataset coverage measurements: [`docs/data-licenses.md`](docs/data-licenses.md).
