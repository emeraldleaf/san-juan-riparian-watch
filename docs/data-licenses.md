# Data licences and attribution — can we train on this?

**Short answer: yes.** Every third-party dataset this project trains on is openly licensed. But
**ShareAlike has teeth**, and one dataset that *sounds* usable for our AOI **contains no data there at
all**. Both facts are below, because getting either wrong invalidates everything downstream.

See CLAUDE.md.

## The licences

| Dataset | Licence | Train on it? | Attribution |
|---|---|---|---|
| **CSU field points** (`TabletData_2017.csv`) | **CC BY-SA 4.0** | ✅ yes | Vorster et al. (2018), *Data* 3(4):42 |
| **CSU tamarisk probability, 2016** (GeoTIFF) | **CC BY-SA 4.0** | ✅ yes — **but not in our AOI**, see below | Evangelista et al. (2018), CSU/NREL |
| **CSU valley bottoms** (VBET, whole basin) | **CC BY-SA 4.0** | ✅ yes | Evangelista et al. (2018), CSU/NREL |
| **CO-RIP** (Dryad) | open (Dryad); verify terms on download | ✅ as **weak** labels | Woodward et al. (2018), *ISPRS IJGI* 7(10):397 |
| **NMRipMap** (NM Natural Heritage / UNM) | public MapServer; verify terms for redistribution | ✅ | Muldavin et al. (2023) |
| Sentinel-2 / Landsat / NAIP (Planetary Computer) | open | ✅ | ESA / USGS / USDA |

Verified from the DSpace metadata (`dc.rights.uri = https://creativecommons.org/licenses/by-sa/4.0/`),
not from a README's say-so.

## 🔴 ShareAlike — what it actually binds

**CC BY-SA 4.0 requires that *adapted material* be released under the same licence.** For this project
that is not academic:

- ✅ **Training on it is permitted**, including commercially. Attribution is mandatory.
- ⚠️ **Derived *data products* are adapted material** — a label layer, a probability raster, a
  reach-level invasive-cover map built from their data must be **CC BY-SA 4.0**. We cannot publish a
  derived map under a more permissive licence, and must not imply otherwise.
- ⚖️ **Model weights are legally unsettled.** Whether trained weights constitute a derivative of the
  training data is genuinely contested. **We take the conservative position:** any published weights
  or derived products are released **CC BY-SA 4.0 with attribution**. That costs this project nothing
  — it is an open-science project — and pretending the question is settled would be dishonest.
- 🧩 **Code is separate.** Licences on data do not reach code that merely reads it. The repo's source
  licence is its own decision (see the open item below).

**Practical consequence:** the outputs of Stage 2 and Stage 3 — the invasive-cover and change products
— are **CC BY-SA 4.0**, because they are built from CC BY-SA labels. Plan on that; do not discover it
at publication.

## 🔴 Technical usability ≠ licence. Measure the coverage.

A dataset can be perfectly licensed and still useless to you. **We measured, rather than assumed:**

| Dataset | Covers the San Juan? | Usable for training **in our AOI**? |
|---|---|---|
| **CSU field points** | ✅ 167 records (49 Russian olive, 47 tamarisk) | ✅ — **but 0 defoliated points**; train the beetle head on the [ecoregion-matched Plateau pool](decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md) and transfer |
| **CSU tamarisk probability 2016** | ❌ **0 valid pixels** — measured | ❌ **No.** Covers the **Dolores** (36,114 px) and **Green** (121,070 px). Their *"select* Landsat scenes" means what it says. |
| **CSU valley bottoms (VBET)** | ✅ whole basin | ✅ — the *"maximum riparian corridor extent"*, i.e. what our HAND envelope re-derives. **The most directly useful of the three in our AOI.** |
| **CO-RIP** | ✅ whole basin | ✅ as **confidence-weighted weak labels** — 0.55 in the Southern Rockies, where it over-predicts |
| **NMRipMap** | ✅ NM only | ✅ — the strongest labels we have, but **not in Colorado** |

**The tamarisk probability raster is the trap.** It is exactly the product you would reach for, it is
openly licensed, it is small, and **there is nothing in it for the San Juan.** It is still valuable —
as a **method benchmark on the Dolores**, same Colorado Plateau ecoregion, a river *Diorhabda* was
released on, and ground the incumbent claims. Just not as training data for us.

## Attribution (required — CC BY-SA)

> **Vorster, A., Evangelista, P., West, A., et al. (2018).** *Tamarisk and Russian Olive Occurrence and
> Absence Dataset Collected in Select Tributaries of the Colorado River for 2017.* Data 3(4):42.
> CC BY-SA 4.0.
>
> **Evangelista, P., Young, N., Vorster, A., West, A., Hatcher, E., Woodward, B., Anderson, R., &
> Girma, R. (2018).** *Mapping Native and Non-Native Riparian Vegetation in the Colorado River
> Watershed.* CSU Natural Resource Ecology Laboratory / USGS / NASA DEVELOP. CC BY-SA 4.0.
>
> **Woodward, B., Evangelista, P., Vorster, A., et al. (2018).** *CO-RIP: A Riparian Vegetation and
> Corridor Extent Dataset for Colorado River Basin Streams and Rivers.* ISPRS Int. J. Geo-Inf. 7(10):397.
>
> **Muldavin, E., et al. (2023).** *New Mexico Riparian Habitat Map (NMRipMap) Version 2.0 Plus.*
> New Mexico Natural Heritage Program, University of New Mexico.

## Open

- 🔴 **The repository has no LICENSE file.** It is public, and it already ingests CC BY-SA data. With
  no licence, the default is *all rights reserved* — which is the worst of both worlds for a portfolio
  project: nobody may reuse the code, and our licence obligations for the data are unstated. **Decide
  the source licence** (permissive for code is normal and compatible), and state the data-products
  licence as CC BY-SA 4.0 alongside it.
- Confirm CO-RIP's Dryad terms and NMRipMap's redistribution terms **on download**, rather than
  assuming from the landing pages.
