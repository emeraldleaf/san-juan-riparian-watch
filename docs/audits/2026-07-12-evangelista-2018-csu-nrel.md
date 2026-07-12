# Prior-art audit — Evangelista et al. (2018), CSU/NREL

**Date:** 2026-07-12 · **Method:** `/paper-audit` · **Verdict:** 🟠 **RETRACTS**
**Outcome:** falsified our Novelty Claim 1. Claim rewritten, narrower and true.

## The paper

> **Evangelista, P., Young, N., Vorster, A., West, A., Hatcher, E., Woodward, B., Anderson, R., &
> Girma, R. (2018).** *Mapping Native and Non-Native Riparian Vegetation in the Colorado River
> Watershed.* Natural Resource Ecology Laboratory, Colorado State University; USGS; NASA DEVELOP.
> Prepared for the Walton Family Foundation. 30 January 2018.
> [Report PDF](https://static.waltonfamilyfoundation.org/67/93/2f16c8d64dcab074c02f0c6f1857/mapping-riparian-vegetation-co-river.PDF)
> · [Project page](https://www.nrel.colostate.edu/improved-rip-maps-crb/)

| | |
|---|---|
| Sensors | **Landsat 5 TM (2006) and Landsat 8 OLI (2016)**, 30 m; Sentinel-2A tested in case studies |
| Epochs | **2006 and 2016** — two, not a series |
| Extent | Colorado River Basin (~630,000 km²); species products on *select* reaches |
| Model | Random Forest (Google Earth Engine) |
| Labels | Field points + digital sampling; *"cannot be shared entirely due to data use agreements"* |
| San Juan | **Yes** — Russian olive mapped there for 2006 and 2016 (NASA DEVELOP) |

## What we had claimed (and where)

`docs/literature-review.md`, `docs/STATUS.md`, `README.md`, `docs/index.md`, and the Stage-2 spec
all asserted, in some form:

> *"CSU/NREL's 2018 dataset gives 3,000+ tamarisk/Russian-olive occurrence points **but no map** …
> **Nobody has produced** a wall-to-wall, time-series, native-vs-invasive cover + change product …
> **They were never joined.**"*

**Root cause of the error: we read the project's web page (which foregrounds the point dataset) and
never read the report.**

## The evidence that falsified it — their Products table, verbatim

| Product | Description (quoted) |
|---|---|
| Riparian vegetation digital Mapbook atlas | *"Riparian vegetation for **2006, 2016 and the change between years** for the Colorado River Basin"* |
| Tamarisk occurrence for 2016 digital Mapbook atlas | *"**Select** tamarisk modeling results for 2016 in a Mapbook atlas"* |
| Maximum riparian corridor extent | *"A shapefile that covers the Colorado River Basin created using … VBET"* |
| NASA DEVELOP | *"mapping Russian olive distribution along the **San Juan River in 2006 and 2016**, comparing the same two satellites"* |

They also report change-detection results directly:

> *"An evaluation of the change map in a known region of tamarisk management showed that our models
> did identify a substantial decrease in tamarisk."*

**So a native-vs-invasive map, and a change product, both exist — including on our river.** Claim 1
as written does not survive.

## What they could NOT do — in their own words

This is where the contribution now lives. Their stated constraints are, in effect, a specification.

**1. Landsat cannot resolve the tamarisk phenological signature.**

> *"Differences in seasonal phenology across the study area with tamarisk and native riparian
> vegetation were found to be significant, but the signature between tamarisk and other riparian
> vegetation **did not show to be very different when using Landsat imagery** … **Without a
> different sensor with greater spectral or grain resolution this is a difficult constraint to
> overcome.**"*

Phenology is *the* discriminator in the tamarisk literature (§2.2 of the literature review), and the
incumbent says their sensor cannot see it. Sentinel-2 — 10 m, with red-edge bands — is precisely the
"different sensor with greater spectral or grain resolution" being asked for.

**2. The tamarisk beetle defeated their models.**

> *"One major challenge for mapping tamarisk has been the impacts of the tamarisk beetle … Areas
> that had active beetle activity were **difficult to accurately map** … the live-dead tamarisk mix
> added confusion to model results."*

The biocontrol confound is **unhandled by the incumbent**. Our gap 3 is therefore *confirmed by the
state of the art*, not merely asserted by us.

**3. Two epochs, two different sensors.**

> *"When performing change detection between 2006 and 2016, we relied on two different Landsat
> sensors; Landsat 5 TM and Landsat 8 OLI … this could result in **change maps that show differences
> between sensors in addition to changes in the distribution of a species**."*

A sensor-consistent **annual** series is still not done.

## Coverage map

| Their claim | Our surface | Effect |
|---|---|---|
| Riparian veg map 2006 / 2016 / change, basin-wide | Literature review §2.1, Novelty Claim 1 | **FALSIFIES** "no map / never joined" |
| Tamarisk atlas 2016 (*select* areas) | Novelty Claim 1 | Narrows it — not wall-to-wall, single epoch |
| Russian olive on the **San Juan**, 2006 & 2016 | Novelty Claim 1; Stage-2 spec | **FALSIFIES** "nobody mapped species here" |
| Landsat cannot resolve tamarisk phenology | Stage-2 spec (sensor choice) | **STRENGTHENS** us — justifies Sentinel-2 + dense temporal stack |
| Beetle defoliation confounded the models | Literature review gap 3; Stage-2 spec | **CONFIRMS** the gap; the incumbent hit it and stopped |
| Field DB not fully shareable | Label-scarcity argument (§7) | Supports weak-label mining |

## What changed in the repo

- `docs/RETRACTIONS.md` — new entry `csu-produced-no-map`. The CI gate then **found every document
  still carrying the false claim**, rather than relying on memory: `STATUS.md`, `index.md`, the
  Stage-2 spec, `README.md`.
- Novelty Claim 1 rewritten: **annual, 10 m, beetle-aware** — the three axes the incumbent explicitly
  could not reach.
- Report added to the RAG corpus (`docintel/corpus/seed_sources.yaml`) so the system answers from the
  primary source, not our summary of it.

## Revised novelty claim (falsifiable)

> **No annual, 10 m, beetle-aware, wall-to-wall native-vs-invasive riparian cover + change product
> exists for this basin.**
>
> *Falsified if:* someone shows a species-level product that is annual (not 2-epoch), resolves the
> corridor at ≤10 m, and treats defoliation as a state rather than as absence. Evangelista et al.
> (2018) is 2-epoch, 30 m, and beetle-confounded, and does **not** qualify — **by their own account**.
