# Prior-art audits — the falsification log

Every claim this project makes about being *novel* is a claim about the literature, and therefore a
claim that can be **falsified by a single paper**. This directory is the record of us trying to do
exactly that, to ourselves, on purpose.

Each audit is produced by **`/paper-audit`** (`.claude/commands/paper-audit.md`) and is a citable
record: the paper, the claims extracted, a coverage map against our encoding surfaces, a verdict,
**verbatim evidence**, and what changed in the repo as a result.

> ## Why this is worth publishing
>
> Related-work sections are usually written to justify the contribution. This log is written to
> **attack** it, and it records the attacks that landed. **Three of our claims have been narrowed or
> withdrawn by prior art, two of them after we had already built on them.** That is not a comfortable
> thing to publish, and it is the reason the remaining claim is worth believing.
>
> The log pairs with **`docs/RETRACTIONS.md`**, which is *machine-checked*: once a claim is retracted,
> CI **fails any document still asserting it**. A withdrawn claim cannot quietly survive in a corner
> of the repo — including on the public site, where exactly that had happened.

## The log

| Date | Source | Verdict | What it did to us |
|---|---|---|---|
| 2026-07-17 | [CropGlobe (Tong & Wang 2025)](2026-07-17-cropglobe-tong-2025.md) — *Invariant Features for Global Crop Type Classification* | 🟡 **GAP** | **The FM premise's strongest published challenge — but it does not land as a threat.** Finds simple spectral-temporal features *beat FM embeddings* on cross-geography transfer. **Not** riparian/invasives (crop type), and it tests **frozen embeddings**, not a fine-tuned backbone — the variable our own pre-flight found load-bearing. So it validates our in-tile ties, hardens the go/no-go bar (beat a strong *simple* baseline, not just RF), and names a CropNet-style baseline to add to Phase 1 — but concedes nothing about the product. |
| 2026-07-14 | [Riparian methods vs. the FM fine-tune](2026-07-14-riparian-methods-prior-art.md) — CO-RIP, CSU/Walton, 2017 dataset, Prithvi/SatMAE | 🟡 **GAP + SURVIVES** | **No analogue of the FM weak→strong fine-tune for riparian was found — the contribution survives, narrowly framed.** But the *workflow* (corridor negatives, year-matched labels, overlay-and-look) is **published practice**, not ours: cite it, don't imply we invented it. GAP items: per-pixel decoder (independent support), 30 m→10 m boundary weighting, beetle-state is a *riskier extension*. **Secondary synthesis — the CSU/Walton report still needs a direct `/paper-audit` before Phase 2.** |
| 2026-07-12 | [Perkins et al. (2025)](2026-07-12-perkins-2025-canyonlands.md) — *Riparian Vegetated Area in Canyonlands NP, 1940–2022* | 🟠 **RETRACTS** | **Extent over time is not novel *on its own*.** They mapped riparian vegetated area back to **1940** — further than Landsat reaches. It survives only **qualified**: theirs is aerial, discrete dates, 152 km of one park, *area* not species, **no beetle**. Ours must say *annual, automated, wall-to-wall, satellite, species-level, beetle-aware*. **Confirms the beetle gap a third time** — a 2025 riparian-change paper that never mentions *Diorhabda*. |
| 2026-07-12 | [Evangelista et al. (2018)](2026-07-12-evangelista-2018-csu-nrel.md) — CSU/NREL, *Mapping Native and Non-Native Riparian Vegetation in the Colorado River Watershed* | 🟠 **RETRACTS** | **Falsified Novelty Claim 1.** We said CSU produced "points but no map" and that "nobody has produced a native-vs-invasive cover + change product". They shipped riparian maps for **2006, 2016 and the change between them**, and **Russian-olive maps on the San Juan** for both years. We had read their web page, never the report. Claim rewritten: **annual, 10 m, beetle-aware**. |
| 2026-07-11 | [Woodward et al. (2018), CO-RIP](2026-07-11-corip-woodward-2018.md) — *ISPRS IJGI* 7(10):397 | 🟠 **RETRACTS** | **Killed "we built an RF riparian classifier" as a contribution.** CO-RIP mapped riparian extent for the **entire Colorado Basin, San Juan included**, at median **κ 0.80** — valley-bottom + Random Forest on Landsat. That is our Stage-1 method class, published in 2018. Extent for one epoch is **not** a contribution; it is a baseline. |
| 2026-07-11 | [Tamarisk detection — the established literature](2026-07-11-tamarisk-detection-established.md) (S2+RF 87.8% OA; Landsat 80–91%; senescence phenology) | 🟠 **RETRACTS** | **Killed "we detect tamarisk from satellite" as a contribution.** Settled since ~2005. It also handed us the discriminator (**late-season senescence**) — which then indicted our own harness for mean-pooling the time axis away. |

## Verdict classes

| | Meaning |
|---|---|
| 🔴 **THREAT** | Does, or nearly does, what we claim nobody has done. Stop; re-position. |
| 🟠 **RETRACTS** | Falsifies a claim we publish → `docs/RETRACTIONS.md`, and CI forces every doc into line |
| 🟡 **GAP** | A method/source we should adopt → issue |
| 🔵 **CORPUS** | Sound and relevant, but belongs in the RAG, not the rules → `seed_sources.yaml` |
| ⚪ **COVERED** | Already cited and accurately summarised |
| ⚫ **OUT OF SCOPE** | Different biome/sensor/problem |

## What survives, after three audits

Stated so it can be falsified, which is the point:

> **No annual, 10 m, beetle-aware, wall-to-wall native-vs-invasive riparian cover + change product
> exists for this basin.**

Each qualifier is there because an audit put it there:

- **annual** — because CSU/NREL already did 2-epoch (2006/2016).
- **10 m** — because they used 30 m Landsat, and **state it cannot resolve the tamarisk phenological
  signature**: *"without a different sensor with greater spectral or grain resolution this is a
  difficult constraint to overcome."*
- **beetle-aware** — because *"areas that had active beetle activity were difficult to accurately
  map"*, and no operational classifier we have found handles defoliation as a state rather than as
  absence.
- **native-vs-invasive** — because CO-RIP gives extent without species.

The incumbent's own stated limits are, in effect, the specification for this project. That is a far
stronger position than the one we started with, and we only reached it by being wrong in public.

## CPU pre-flight — the GPU go/no-go evidence (2026-07-16, external session)

**A different category from the audits above.** These are not prior-art falsifications; they are
**CPU benchmarks that answer "is the GPU worth renting?"** with evidence instead of hope. They live
here because the decision memo consolidates them and they carry the same burden of proof.

> ⚠️ **All six benchmarks use Presto (0.82 M params) as a CPU stand-in for OlmoEarth (207.5 M).**
> They tell you *where to look and what bar to beat* — **not** what OlmoEarth will score. The §5
> caveats (S2+NDVI only, light CPU fine-tune, 3 seeds, NM lowland only, temporal transfer
> **unmeasured**) must travel with every number quoted from them.

- [**DECISION MEMO — should we rent a GPU?**](2026-07-16-DECISION-MEMO-olmoearth-gpu.md) — **start
  here.** *Yes, conditionally.* A fine-tuned FM beats RF **only** on hard/label-scarce transfer to
  unseen ground (**+0.04–0.08 ROC**), and ties RF on extent and in-tile. The bar for OlmoEarth-Base:
  **beat fine-tuned Presto's ~0.75, not merely RF** — a free CPU model already beats RF there.
  🔴 **Carries a landing correction**: its `OLMOEARTH_V1_1_BASE` target **does not exist** in the
  pinned stack, which makes §7.2 unexecutable and §7.4's cost ~3× optimistic.
- [Methods review — riparian FM landscape](2026-07-16-riparian-fm-methods-review.md) + the searchable
  corpus — [raw](riparian_methods_corpus.csv) and [OA-linked](riparian_methods_corpus_linked.csv)
  (`+ doi_url, oa_pdf_url, landing_url, openalex_url, is_oa`), built by
  [`enrich_corpus.py`](enrich_corpus.py) (OpenAlex) and fetched by
  [`fetch_corpus_pdfs.py`](fetch_corpus_pdfs.py) (stdlib, resumable, validates `%PDF`).
  **Read the ranking honestly**: only **8 of 320 score ≥7** on method-relevance, and the top-ranked
  paper is *Spartina* in the Yangtze Estuary — method-similar, wrong biome. It is an index to search,
  not a pile to ingest. It also does **not** contain Presto or CropGlobe, the memo's own two
  load-bearing citations (both now added to `docintel/corpus/seed_sources.yaml` by hand).

  > 🔴 **`is_oa` is not `is_fetchable` — measured 2026-07-17.** OpenAlex reports **306 of 320** open
  > with a PDF URL. An actual fetch got **93 (30%)**, 584 MB. The papers really are open (CC BY); the
  > *publishers* block robots. **MDPI alone was 102 of the 213 failures** — and this repo's own
  > `seed_sources.yaml` header had already documented it on 2026-07-11: *"mdpi.com, researchgate.net
  > and www.usgs.gov all return 403 to curl even with a browser User-Agent."* We re-learned it at 213
  > requests.
  >
  > | fetch succeeded | | fetch 403'd / HTML-paywalled | |
  > |---|---|---|---|
  > | arxiv.org | 31 | **mdpi.com** | **102** |
  > | ieeexplore.ieee.org | 23 | doi.org | 21 |
  > | frontiersin.org | 6 | onlinelibrary.wiley.com | 20 |
  > | pubs.usgs.gov · plos · copernicus | 9 | link.springer.com | 15 |
  >
  > An OA licence is a *legal* fact; a 403 is an *access-control* fact. Conflating them is what makes
  > "306 open-access PDFs" read as "306 downloadable PDFs". PDFs, `fetch_failures.csv` (213) and
  > `closed_access.csv` (14) are **gitignored** — the CSV is the reproducible artifact, not 584 MB of
  > publisher PDFs in git.
- [Malpais reach — separability & corridor resolvability](2026-07-16-malpais-reach-generalization-note.md)
  — a second reach against Phase 0's "one reach, not the basin" caveat, and the best evidence yet on
  **S2 10 m vs Landsat 30 m**: the corridor is ~8 px at 10 m but **~3 px at 30 m**, where it blurs
  into irrigated agriculture — *precisely* the confound for the native-vs-invasive split.
  ⚠️ Ad-hoc harness, **not** `validate_layer.py` — not comparable to Phase 0's AUC 0.752 until re-run.

Benchmark result notes (the arc the memo consolidates):
[extent, in-tile](2026-07-16-presto-arm-results.md) ·
[species, in-tile](2026-07-16-presto-species-results.md) ·
[cross-tile transfer](2026-07-16-cross-tile-transfer-results.md) ·
[label-budget sweep](2026-07-16-label-budget-sweep-results.md) ·
[fine-tune transfer](2026-07-16-finetune-transfer-results.md) ·
[**three-tile transfer**](2026-07-16-three-tile-transfer-results.md) (the decisive control).

## Still to audit

- ~~**CropGlobe (Tong et al. 2025)**~~ → **audited 2026-07-17** (🟡 GAP, above): a real challenge to
  the FM *premise* (simple features beat FM *embeddings* on transfer), but not a product threat — it
  tests frozen embeddings, not the fine-tuned backbone our bet rides on, and it is crop type, not
  riparian. Left us a Phase-1 baseline to add (issue below).
- **CSU/Walton report** — carried over from the
  [methods audit](2026-07-14-riparian-methods-prior-art.md): the closest procedural analogue for the
  invasives half, still only known to us second-hand.
- Anything the `/paper-audit` command is pointed at. Run it before building on a novelty claim, not
  after.
