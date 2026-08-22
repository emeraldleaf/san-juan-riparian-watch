---

> **✅ Re-verified (2026-08-21) — the result stands; only the label was wrong.** The RF-vs-FM transfer result holds: the RF bar reproduced (Farmington 0.90 / Kirtland 0.85 / Aztec 0.89 / Malpais 0.56), and RF and FM were scored on the **same held-out pixels** (NMRipMap has no labels up the wash). What is retracted is only the **“desert arroyo” descriptor** — “Malpais” is the **river-dominated subwatershed** HUC12 “Malpais Arroyo–San Juan”, so **attribution to arroyo morphology is unverified**. The real mechanism: on the one **out-of-distribution** held-out reach the pixel-wise RF collapses to near-chance (0.56) while OlmoEarth holds (0.89) — brittleness to distribution shift, not an arroyo rescue and not invasive-specific (RF near-chance on native 0.59 AND invasive 0.53). See [RETRACTIONS.md](RETRACTIONS.md) → `arroyo-rescue-attribution-2026-08-21`.
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
| **[▸ Live story map — ask the agent](story.html)** | The scrollytelling tour of the findings (23% invasive corridor · the RF-vs-foundation-model arroyo *result*, **0.557 vs 0.889 AUROC** · the beetle-control null · the pre-2000 negative) over the live Farmington map, ending in a **grounded, cited AI agent** you can ask. |
| **[▸ Interactive method map](method-map.html)** | The whole method, made explorable — inputs → the phenology data cube → RF vs a fine-tuned foundation model → the output maps (with the real chips) → the honest findings, plus a guided Q&A. **Start here for the visual tour.** |
| **[▸ Live extent map — Bloomfield reach](extent-map.html)** | The actual **product** artifact: predicted riparian extent (8,511 polygons, 8.0% of the AOI) from the pooled RF, over a reach it never trained on, on satellite imagery. The honest RF baseline the foundation model must beat. |
| **[▸ FM vs RF — the out-of-distribution reach](fm-vs-rf-malpais.html)** | **Verified 2026-08-21 — the result stands; only the label was wrong.** The "Malpais" fold is the **river-dominated** "Malpais Arroyo–San Juan" HUC12 — a San-Juan-valley subwatershed, not a desert arroyo (*attribution to arroyo morphology is unverified*). But the RF bar reproduced and RF and FM were scored on the **same held-out pixels**, so RF 0.557 → FM 0.889 **holds**. On this **out-of-distribution** reach the pixel-wise RF collapses to near-chance (0.56) while OlmoEarth holds (0.89) — brittleness to distribution shift, not an arroyo rescue and not invasive-specific. Post-mortem: **[the reach-provenance gap](2026-08-21-reach-provenance-gap.md)**. (Earlier, narrower catch: [map-extent artifact](2026-08-10-arroyo-map-extent-artifact.md).) |
| **[▸ FM vs RF — the deployable map (Bloomfield)](fm-vs-rf-bloomfield.html)** | Both models deployed over an unseen reach: FM (green) vs RF (orange) vs NMRipMap truth. On a well-sampled river they agree closely — the FM's edge is on the hard morphologies. |
| **[▸ Riparian corridor vs invasive (Farmington)](extent-vs-invasive.html)** | The product a watershed manager actually wants: the green riparian-woody corridor (7.6 km²) with the invasive tamarisk/Russian-olive share **within** it (1.7 km²) in red. **23% of the corridor is invasive** — a figure the model reproduces from the NMRipMap labels it was trained on (in-sample calibration, not an independent validation). Present-day, label-anchored. |
| **[Engineering & methodology walkthrough](engineering-review.html)** | How the pipeline works end to end — STAC satellite ETL, weak-label and reference-trained delineation, spatial cross-validation, RF vs OlmoEarth, the PostGIS medallion schema, the C# API and the MapLibre map — with **verbatim code** and a *"where a reviewer should attack this"* section. |
| **[Literature review](literature-review.md)** | What has already been done, and why this project is not duplicating it. Written so the novelty claim can be **falsified**, not just asserted. |
| **[Stage 2 spec — invasive vs native cover (Tamarix)](specs/2026-07-11-stage2-invasives-tamarix.md)** | The product thesis, the phased class schema, the trade-offs accepted, and what was **cut and why**. |
| **[Invasive FM-vs-RF LORO — pre-registered plan](specs/2026-08-21-invasive-fm-vs-rf-loro.md)** | The extent LORO proved the FM's robustness to distribution shift; whether that extends to **native-vs-invasive discrimination is untested**. This pre-registers the same rigorous LORO for the invasive task — measure it, don't infer it. |
| **[CAG vs CRAG on the project canon — pre-registered](specs/2026-08-22-cag-vs-crag-project-canon.md)** | Retrieval was the default when this stack was written; context windows grew and caching arrived, and the choice was never re-tested. Measures whether caching the **158k-token project canon** in context beats the graded retrieval we run today — on correctness, **citation validity**, and cost at this traffic. A per-source question, not an architecture religion. |

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

- [Basin-scale productionization — wall-to-wall riparian + invasive, annually](decisions/2026-08-21-basin-scale-productionization.md)
  — how the four-reach experiment becomes a recurring basin product: classify the **hydrography buffer**
  (not the whole basin), tile it, drive a resumable `(tile, year)` manifest, stream imagery + two-stage
  GPU inference (OlmoEarth extent, invasive when its LORO clears), on a batch orchestrator, with a cost
  model measured from a one-HUC10 proof. Honest validation-at-scale, since you can't hand-check a basin.
- [The conversational map agent — one loop core, two policies](decisions/2026-08-18-map-agent-runtime.md)
  — a **second agent** on the platform without forking the runtime: factor the tool loop into a generic
  **core** and a per-agent **policy** (soul, registry, seed, empty-fallback, citation). The document
  path stays byte-identical (defaults); its tests are the gate. Read-only tools and "resolve, don't
  guess" hold across both. Includes the [runtime diagram](map-agent-runtime.svg).
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

- [**The data-cube technique**](2026-07-18-reach-cube-materialization.md) — how a bare bounding box
  becomes a **phenologically-aligned Sentinel-2 time-series cube** per reach: STAC indexing + COG
  range-reads + **12-month median mosaics** + label-driven windowing + verify-don't-trust. Includes
  an honest tooling assessment (`odc-stac`/dask as the portable core, rslearn as the ML adapter, GEE
  as the server-side alternative) and the **receipt** — a mis-composited shortcut collapsed a transfer
  to AUC 0.37. Reusable via
  [`materialize_reach.py`](../experiments/riparian_extent/materialize_reach.py); the flow is
  drawn in [`malpais-download-pipeline.svg`](malpais-download-pipeline.svg).

- [**Methods & metrics**](2026-07-18-methods-and-metrics.md) — the companion to the results: what the
  two models (RF, foundation model) *are*, what every number means (**AUC, F1, precision, recall,
  accuracy** — and why accuracy lies under class imbalance), what **overfitting** is and what we're
  fitting, and why the evaluation is fair (spatial splits, prevalence-invariant AUC, head-to-head on
  identical footing, **cross-reach transfer as the verdict**). Covers both tasks — extent
  (riparian-vs-other) and invasives (invasive-vs-native).

## Prior-art audits — the falsification log

- [**Prior-art audits**](audits/) — every claim this project makes about being *novel* is a claim
  about the literature, and a single paper can falsify it. This is the record of us trying to do
  exactly that, **to ourselves, on purpose** — of the four attacks that landed on the *product*
  claim, and of a fifth on the *method*: [riparian methods vs. the FM
  fine-tune](audits/2026-07-14-riparian-methods-prior-art.md), where the foundation-model
  contribution **survives** but the surrounding workflow turns out to be published practice we must
  cite, not invent. Paired with [Retractions](RETRACTIONS.md), which is **machine-checked**: once a
  claim is retracted, CI fails any document still asserting it.

## Reference

- [Data licences & attribution](data-licenses.md) — **can we train on this?** Yes: the CSU datasets
  are **CC BY-SA 4.0**. But **ShareAlike binds our outputs** (derived maps must be CC BY-SA too), and
  the tamarisk probability raster — the one you'd reach for — contains **0 pixels over the San Juan**.
  Measured, not assumed.
- [Data sources](data-sources.md) — every source, its endpoint, and the trap in each.
  **NMRipMap is classified** (filter `L2_Code`, never fetch raw) and its **label vintage is 2020**.
- [Map layers](map-layers.md) — the materialized product GeoJSONs in `web/public/maps/`
  (riparian **RF** + **OlmoEarth FM**, **invasive**, deep-time, truth) and what the `/map` legend
  shows vs. what the agent can still only *display*, not *query*.
- [Retractions](RETRACTIONS.md) — withdrawn claims. CI fails any doc restating one without retracting it.

## Specs

- [Stage 1 — riparian delineation](specs/2026-07-03-stage1-riparian-delineation.md)
- [Stage 2 — invasives / Tamarix](specs/2026-07-11-stage2-invasives-tamarix.md)
- [Stage 3 — annual change](specs/2026-07-04-stage3-annual-change.md)
- [**GPU fine-tune execution plan**](specs/2026-07-12-gpu-finetune-execution-plan.md) — costed, with
  the abort criteria written *before* the money is spent. **Compute is not the constraint** (~$2–5 for
  the control run); the `rslearn` data build is, so it happens locally and for free first.
- [**Phase 3 — deep-time, cross-sensor, beetle-aware change**](specs/2026-07-18-phase3-deeptime-change.md)
  — the actual contribution: annual extent + native-vs-invasive back into the **Landsat era (1984→)**,
  past the pre-beetle baseline. Reopens the RF-vs-FM decision (cross-sensor is the FM's one structural
  edge) and settles it on a **measured** cross-sensor test, not the single-epoch tie. Names the three
  hard truths — no pre-2017 labels, the beetle signal inversion, the 30 m resolution wall — that are
  bigger risks than the model choice.
- [**FM-vs-RF, decided on the deployable map**](specs/2026-07-19-fm-vs-rf-deploy-decision.md) — where
  OlmoEarth **1.1** must earn its keep, on the **`silver.riparian_extent` task only** (invasives out of
  scope). The bar is **measured, not hypothetical**: leave-one-reach-out median-mosaic RF over 4 diverse
  reaches, **macro-mean AUC 0.798** (arroyo fold 0.557 — PR #71). **GO** requires the FM to clear a written,
  exhaustive contract — a **Transfer win** *(macro-mean ≥ +0.04 with a cluster-aware **reach-block-bootstrap**
  CI > 0, **or** the arroyo fold ≥ +0.04 significant with no other fold significantly regressing)*, **or** a
  Transfer **tie** (no win, no significant regression) plus **Coherence** *(≥ 2 of 3 on the 4-fold macro-mean:
  speckle ≤ ½ RF, connectivity ≥ +0.10, Moran's I ≥ RF, at matched ≥ 0.80 recall)*. Calibration (macro-mean
  ECE vs RF + 0.02) is a **guard only** — it scopes recalibration work into a GO, never flips the decision.
  Every non-GO leaf is **ABORT → RF ships**, with a number.
- [**Stage 2 — native-vs-invasive, and does it survive the beetle**](specs/2026-08-01-stage2-invasives-beetle-gate.md)
  — the Stage-1 LORO method pointed at the **actual novelty** (native vs Tamarix/Russian-olive over the
  deep record). Three nested tests (separability gate · species LORO · the **beetle axis isolated**), with
  the headline prediction **pre-registered**: a present-day-trained model **inverts** pre-beetle (AUROC < 0.5)
  because the beetle *flips the sign* of the tamarisk phenology cue — the confound turned into a number.
  The CPU RF arm ([`phase3c_invasives_beetle.py`](../experiments/riparian_extent/phase3c_invasives_beetle.py))
  is scaffolded and GPU-free — the highest information-per-dollar next move.
- [Document intelligence (RAG)](specs/2026-07-04-document-intelligence-rag.md)
- [**Conversational map agent**](specs/2026-08-18-conversational-map-agent.md) — a Shippy-shaped analysis agent: ask the map in plain language, get cited answers while it moves. *Resolve, don't guess* — a typed CLI, isolated sessions, and whole-agent rubric evals.

## Results

- [**Invasive extent over time — a robustness cautionary tale, and the reliable map it pointed to**](2026-08-05-invasive-extent-over-time.md)
  — the honest arc: mapping invasive extent *back through Landsat* is **not robust before ~2000** (four
  fixes — bracketing, 5-year windows, spectral indices, radiometric normalization — stabilised 2000–2010
  but never the pure-TM 1990, which swings ~1 pp regardless), so **no trajectory can be claimed**. What it
  delivered instead is the reliable **[present-day corridor-vs-invasive map](extent-vs-invasive.html)**:
  **23% of Farmington's corridor is invasive** — the model reproduces the NMRipMap label proportion (in-sample calibration, not an independent validation).
- [**The arroyo map that didn't hold water — a spatial claim built on unequal extents**](2026-08-10-arroyo-map-extent-artifact.md)
  — the FM-vs-RF arroyo map overlaid layers of different extent (RF ~1/5 of FM/truth), so "RF fires in
  one corner" was an export artifact read as model behavior. The **0.557 vs 0.889** metric stands; the
  picture didn't. Caught by a reviewer's question — the method working as intended.
- [**The beetle didn't break the discriminator — and the control proves we couldn't have seen it if it had**](2026-08-04-phase3c-beetle-null-result.md)
  — the Stage-2 beetle-inversion CPU/RF arm, run on the real CSU field points. The pre-registered
  prediction (tamarisk-vs-native inverts pre-beetle) is **falsified** — it holds 0.81–0.86 across
  2020→2000 — and the pre-registered Russian-olive control **cratered 0.34**, vetoing the ~0.05 signal
  as cross-sensor/small-sample noise. A clean negative with a clear cause: this in-basin data can't
  resolve the beetle effect; the FM arm and the C2 defoliation test are the way forward.
- [**FM-vs-RF, settled — the foundation model rescues the arroyo, ties on rivers**](2026-08-01-fm-vs-rf-loro-result.md)
  — the deploy decision, answered with a number. Fine-tuned OlmoEarth, leave-one-reach-out, unbiased
  test/val split: it **ties** the RF on the three river reaches (0.81–0.89 vs 0.85–0.91) and **rescues
  the arroyo** (RF 0.557 → **FM 0.889**), lifting the macro-mean to **0.872 vs 0.798**. **GO — but the FM
  is a specialist for hard morphology, not a uniform upgrade.** Layered newcomer→practitioner write-up,
  with the honest limitations a reviewer would raise.
- [**The RF transfer bar — diverse-reach pooling closes it, except the arroyo**](2026-07-20-diverse-reach-transfer.md)
  — the honest baseline for the FM decision. Training on **morphologically diverse** reaches lifts
  cross-reach transfer to **0.85–0.91** on river corridors (RF is genuinely good), but the lone
  **arroyo** stays at **0.557** — the one place a per-pixel RF can't reach, and exactly the
  under-represented-morphology transfer the foundation model is predicted to win. Sharpens FM-vs-RF to a
  single falsifiable test. Reproducible via [`deploy_extent_map.py`](../experiments/riparian_extent/deploy_extent_map.py).
- [**Phase 3B — the temporal gate**](2026-07-18-phase3b-temporal-result.md) — going back three years
  is essentially **free**: an RF trained on 2020 and scored at the same 167 CSU points on **Landsat
  2020 vs Landsat 2017** loses only **+0.003 AUC**. With 3A, both model-agnostic deep-time axes are now
  measured and cheap (sensor +0.046, time +0.003); the binding constraint is **spatial coverage of
  training**, not the year or sensor — so it does not reopen RF-vs-FM. Reproducible via
  [`phase3b_temporal.py`](../experiments/riparian_extent/phase3b_temporal.py).
- [**Phase 3A — the cross-sensor gate**](2026-07-18-phase3a-cross-sensor-result.md) — the first
  deep-time measurement: an RF trained on **Sentinel-2 2020** and scored on the **same held-out
  pixels' Landsat 2020** loses only **+0.046 AUC** (0.942 → 0.896). On the one axis where the
  foundation model has a structural edge — multi-sensor pretraining — a plain per-pixel RF crosses
  sensors cheaply, so the FM edge is **not decisive** here. Isolates the sensor axis only; temporal
  drift (3B) and the beetle inversion (3C) are separate, unsolved and **model-agnostic**. Reproducible
  via [`phase3a_cross_sensor.py`](../experiments/riparian_extent/phase3a_cross_sensor.py).
- [**Phase 0 — the record**](2026-07-14-phase-0-record.md) — what we built (label layer, imagery
  validation, S2 cube, NANO dry-run), the **seven traps** it caught for $0 that would have failed on
  a GPU, the methods that generalised, the trade-offs, and the **open decisions before Phase 1**
  (chiefly: per-window vs per-pixel decoder). Exit gate MET — val_loss 1.455 → 1.428 → 1.401.
- [**GPU extent control — the result**](2026-07-18-gpu-extent-control-result.md) — the Phase-1 control
  ran on a rented A6000: fine-tuned OlmoEarth-Base reaches **riparian F1 ≈ 0.82** (reproduced ×2),
  below RF (0.90–0.92) but above the fine-tuned-Presto bar. A per-pixel diagnostic (confusion matrix +
  NAIP overlays) traces the ceiling to real over-prediction + a coarse decoder; `patch_size: 2 → 1`
  sharpens it and lifts precision, though the size of the F1 gain is **not yet settled** across eval
  protocols. Pipeline validated end-to-end.
- [OlmoEarth vs the RF baseline](olmoearth-vs-rf-baseline.md) — **a retraction, and a hypothesis
  that failed.** The published RF 0.73 / OlmoEarth 0.46 result is withdrawn: the ground truth was
  ~45% wrong, the model's time axis was averaged away, and the labels were four years older than
  the imagery. Fixing the pooling was supposed to be the explanation — it wasn't (F1 0.021 →
  0.065, against the baseline's 0.701). The twist: **the corrupted labels had been *flattering* the
  foundation model**, because they rewarded predicting corridor membership, which a frozen
  embedding is good at.

---

*Source: [github.com/emeraldleaf/san-juan-riparian-watch](https://github.com/emeraldleaf/san-juan-riparian-watch)*
