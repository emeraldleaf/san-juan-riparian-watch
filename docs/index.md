---
layout: default
title: San Juan Riparian Watch
---

# San Juan Riparian Watch

Basin-scale **riparian delineation, invasive-species cover, and change monitoring** for the
San Juan River watershed (Colorado + New Mexico). Learns *where riparian vegetation actually is*
from satellite time series instead of assuming a fixed distance from a stream, then asks the
question that actually matters to a watershed manager:

> **A reach is not healthier just because it is greener.**
> Total riparian cover can rise while the corridor degrades — because the rise is *Tamarix*
> (saltcedar) replacing cottonwood and willow.

---

## Start here

| Document | What it is |
|---|---|
| **[Engineering & methodology walkthrough](engineering-review.html)** | How the pipeline works end to end — STAC satellite ETL, weak-label and reference-trained delineation, spatial cross-validation, RF vs OlmoEarth, the PostGIS medallion schema, the C# API and the MapLibre map — with **verbatim code** and a *"where a reviewer should attack this"* section. |
| **[Literature review](literature-review.md)** | What has already been done, and why this project is not duplicating it. Written so the novelty claim can be **falsified**, not just asserted. |
| **[Stage 2 spec — invasive vs native cover (Tamarix)](specs/2026-07-11-stage2-invasives-tamarix.md)** | The product thesis, the phased class schema, the trade-offs accepted, and what was **cut and why**. |

---

## The honest positioning

Three findings that a reviewer should know up front, because they are uncomfortable and they
are in the docs rather than buried:

**1. Riparian extent mapping is already solved for this basin.**
[CO-RIP](https://www.mdpi.com/2220-9964/7/10/397) (Woodward et al. 2018) mapped riparian corridor
and vegetation for the *entire* Colorado River Basin — **including the San Juan** — using
valley-bottom delineation + Random Forest on Landsat, median **κ 0.80**. Our RF baseline is the
same method class. *"We built an RF riparian classifier" is not a contribution.*

**2. Tamarisk detection is established, and the mechanism is known.**
Sentinel-2 + RF reaches **87.8% overall accuracy**; the discriminator is **phenology** —
specifically *late-season senescence*, because Tamarix holds green after natives brown.

**3. …but the beetle inverts that signal, in exactly our basin.**
The tamarisk beetle (*Diorhabda carinulata*) was **released directly on the San Juan River in
2004–2007** and had saturated the Upper Basin by 2014. **Defoliated Tamarix browns *early***,
inverting the discriminator the entire literature depends on. So a greenness decline in a Tamarix
reach **is not recovery** — it may be biocontrol working. There is no un-confounded control area
inside the study area.

**The actual gap — corrected 2026-07-12, against ourselves.** We used to say *"CSU produced points,
not a map; nobody has joined them."* **That was wrong**, and an audit of the source report (rather
than its web page) found it. **Evangelista et al. (2018)** shipped riparian-vegetation maps for
**2006, 2016 and the change between them**, and Russian-olive maps **on the San Juan for 2006 and
2016**.

The gap survives, narrower and better grounded — **in the incumbent's own words**. They report that
**Landsat cannot resolve the tamarisk phenological signature** (*"without a different sensor with
greater spectral or grain resolution this is a difficult constraint to overcome"*), and that
**beetle defoliation confounded their models**. Theirs is **2-epoch, 30 m, beetle-confounded**.

**What does not exist: an annual, 10 m, beetle-aware, wall-to-wall native-vs-invasive product.**
That is what this project is for — and their recommendation is, in effect, its specification.

---

## Decision records

- [Train the beetle model on the ecoregion-matched Colorado Plateau](decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md)
  — **zero defoliated points fall inside the San Juan.** The beetle's 2017 impact was ecoregionally
  split (Escalante 21.6% live tamarisk; Arizona **87%** live), so training defoliation on the lower
  basin would transfer across an ecoregion boundary — exactly what CO-RIP's κ 0.42–0.90 range warns
  against. Train on the Plateau, validate on the San Juan, and say plainly that it is transfer.
- [Fine-tune OlmoEarth on invasives, with extent as a calibration control](decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md)
  — **the contribution is the *time axis*.** Every existing product is one frozen epoch; nobody has
  an annual riparian product for this basin, of extent or of species. Also records why the beetle
  confound has no un-confounded *place* but does have an un-confounded *time*, and why training
  imagery must match the 2020 label vintage.
- [Confidence-weighted label crosswalk](decisions/2026-07-11-confidence-weighted-label-crosswalk.md)
  — no source is ground truth; every label carries a source, a class, and a confidence. Records
  the two labelling failures that motivated it.
- [Model artifacts, inference, and hosting](decisions/2026-07-11-model-and-inference-hosting.md)
  — HuggingFace weights + on-demand batch inference + a static map demo. Explicitly **no
  always-on GPU**.
- [Delineation over hydrology buffers](decisions/2026-07-03-delineation-over-hydrology-buffers.md)
- [Document-intelligence subsystem](decisions/2026-07-04-document-intelligence-subsystem.md)
- [NextAurora rules applicability](decisions/2026-07-04-nextaurora-rules-applicability.md)

## The method — AI-assisted research that catches its own errors

- [**The method**](method.md) — **a companion to the science, not a footnote to it.** The failure mode
  of AI-assisted research is work that is fast, fluent, plausible and **wrong**, and invisible
  precisely because it looks finished. Exhortation does not fix that; **gates do.** Every mechanism is
  justified by a dated failure it actually caught — including the retracted result that stayed live on
  this very site, the novelty claim a 2018 paper had already falsified, and the hypothesis we tested
  and **disproved**. Also records what *didn't* work: **every documentation-only surface drifted**, and
  a broken gate is worse than no gate because it reports "clean".

- [**The engineering method**](engineering.md) — the counterpart: specs → rules → **gates** → review →
  correction. 10 engineering defects and what caught each (a SQL-injection weakening that CI,
  SonarQube, 20 unit tests and a human review all passed; six ETL bugs that silently corrupted data
  without crashing). Ends with **the gaps**, which is the useful part: **the subsystem with the worst
  defect record is the one with the weakest gate.**

## Prior-art audits — the falsification log

- [**Prior-art audits**](audits/) — every claim this project makes about being *novel* is a claim
  about the literature, and a single paper can falsify it. This is the record of us trying to do
  exactly that, **to ourselves, on purpose** — and of the three attacks that landed.
  Paired with [Retractions](RETRACTIONS.md), which is **machine-checked**: once a claim is retracted,
  CI fails any document still asserting it.

## Reference

- [Data licences & attribution](data-licenses.md) — **can we train on this?** Yes: the CSU datasets
  are **CC BY-SA 4.0**. But **ShareAlike binds our outputs** (derived maps must be CC BY-SA too), and
  the tamarisk probability raster — the one you'd reach for — contains **0 pixels over the San Juan**.
  Measured, not assumed.
- [Data sources](data-sources.md) — every source, its endpoint, and the trap in each.
  **NMRipMap is classified** (filter `L2_Code`, never fetch raw) and its **label vintage is 2020**.
- [Retractions](RETRACTIONS.md) — withdrawn claims. CI fails any doc restating one without retracting it.

## Specs

- [Stage 1 — riparian delineation](specs/2026-07-03-stage1-riparian-delineation.md)
- [Stage 2 — invasives / Tamarix](specs/2026-07-11-stage2-invasives-tamarix.md)
- [Stage 3 — annual change](specs/2026-07-04-stage3-annual-change.md)
- [Document intelligence (RAG)](specs/2026-07-04-document-intelligence-rag.md)

## Results

- [OlmoEarth vs the RF baseline](olmoearth-vs-rf-baseline.md) — **a retraction, and a hypothesis
  that failed.** The published RF 0.73 / OlmoEarth 0.46 result is withdrawn: the ground truth was
  ~45% wrong, the model's time axis was averaged away, and the labels were four years older than
  the imagery. Fixing the pooling was supposed to be the explanation — it wasn't (F1 0.021 →
  0.065, against the baseline's 0.701). The twist: **the corrupted labels had been *flattering* the
  foundation model**, because they rewarded predicting corridor membership, which a frozen
  embedding is good at.

---

*Source: [github.com/emeraldleaf/san-juan-riparian-watch](https://github.com/emeraldleaf/san-juan-riparian-watch)*
