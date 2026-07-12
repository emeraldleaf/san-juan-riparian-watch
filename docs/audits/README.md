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

## Still to audit

- Anything the `/paper-audit` command is pointed at. Run it before building on a novelty claim, not
  after.
