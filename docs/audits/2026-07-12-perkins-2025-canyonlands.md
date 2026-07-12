# Prior-art audit — Perkins et al. (2025), Canyonlands riparian vegetated area 1940–2022

**Date:** 2026-07-12 · **Method:** `/paper-audit` · **Verdict:** 🟠 **RETRACTS (partial)**
**Outcome:** *"extent over time is novel on its own"* is **too strong**. Qualified, and it survives.

## The paper

> **Perkins, D. W., et al. (2025).** *Riparian Vegetated Area in Pre‐Dam, Post‐Dam, and Environmental
> Flow Periods in Canyonlands National Park From 1940 to 2022.* **River Research and Applications.**
> [Paper](https://onlinelibrary.wiley.com/doi/10.1002/rra.4395) ·
> [NPS summary](https://www.nps.gov/articles/000/ncpn-riparian-vegetation-response.htm)

| | |
|---|---|
| **What is mapped** | **Vegetated *area*** (>50% cover). **Not species.** Native vs non-native are **not** separated. |
| Period | **1940–2022** — framed as three regimes: pre-dam (1940–66), hydropower (1966–91), environmental flows (1992–2022) |
| Imagery | **Aerial imagery**, discrete acquisition dates — *not* an automated satellite classification |
| Extent | **152 km** of the Colorado and Green rivers, **inside Canyonlands NP**. Not the San Juan. Not basin-wide. |
| Question | Did three decades of environmental flows reverse channel narrowing? (a **flow-regime** question) |
| **Tamarisk beetle** | **Not mentioned at all** — in a 2025 paper on riparian change in this basin |

## What it falsified

Two documents claimed, without qualification:

> *"**Extent over time** — an annual riparian-extent series. CO-RIP is one epoch; this is the movie,
> not the frame. **Novel on its own.**"*

**"Novel on its own" does not survive.** Long-term riparian *vegetated-area* change in the Colorado
Basin has been mapped, back to **1940** — further back than our Landsat record can reach. Saying
"nobody has looked at riparian extent over time" would have been false, and we were one sentence away
from saying it in a publication.

## What it does NOT falsify — and the qualifiers are load-bearing

| Their work | Ours |
|---|---|
| Vegetated **area** | **Species** — native vs invasive |
| **Aerial imagery**, hand-interpreted, discrete dates | **Automated**, satellite (S2 10 m / Landsat 30 m) |
| **152 km, one national park** | **Wall-to-wall**, basin |
| Three **regimes** over 82 years | **Annual** |
| **No beetle** | Defoliation as a **state** |

So the claim stands **once qualified**:

> **No annual, automated, wall-to-wall, satellite-derived riparian extent product exists for this
> basin** — and none at all at species level with defoliation handled.

That is a narrower sentence than the one we had, and unlike it, it is true.

## And it confirms the beetle gap for the third time

A **2025** paper on riparian vegetation change in the Colorado Basin, explicitly discussing tamarisk
encroachment, **does not mention *Diorhabda* at all**. The biocontrol confound remains unhandled by:

- CSU/NREL (2018) — who hit it and said so: *"areas that had active beetle activity were difficult to
  accurately map"*;
- the operational tamarisk-detection literature;
- and now the most recent long-term riparian-change study in the basin.

Gap 3 has now been independently confirmed three times. It is the least speculative part of this
project's contribution.

## Coverage map

| Their claim | Our surface | Effect |
|---|---|---|
| Riparian vegetated area mapped 1940–2022 | Stage-3 spec; fine-tune ADR ("Novel on its own") | **RETRACTS** the unqualified claim |
| Aerial, discrete dates, 152 km, one park | the same | **Preserves** it once qualified: *annual, automated, wall-to-wall* |
| Area only — no native/invasive split | Novelty Claim 1 | **Strengthens** — the species gap is untouched |
| No mention of the beetle | Literature review gap 3 | **CONFIRMS**, third independent time |
| Flow-regime framing (dams, environmental flows) | — | Out of scope, but a reminder that flow, not just invasion, drives the extent signal we are modelling |

## What changed in the repo

- `docs/RETRACTIONS.md` — entry `extent-over-time-novel-unqualified`. CI now fails any document that
  calls extent-over-time novel without naming the qualifiers.
- The fine-tune ADR and the Stage-3 spec now state the qualified claim.
- Added to the RAG corpus.

## A note on how this was nearly missed

This paper appeared in the *first* web search run during the CSU audit, and was set aside as "still to
audit". It sat on the to-do list in `docs/audits/README.md` for exactly one day before being picked
up — and it turned out to contain a partial falsification. **Prior art does not wait for a convenient
moment**, and the audit backlog is the most expensive backlog in the project.
