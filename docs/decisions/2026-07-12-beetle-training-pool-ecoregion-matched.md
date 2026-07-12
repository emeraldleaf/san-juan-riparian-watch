# ADR: Train the beetle/defoliation model on the ecoregion-matched Colorado Plateau, not on the whole basin

**Date:** 2026-07-12 · **Status:** Accepted (planning) · **Supersedes:** nothing
**Tracks:** issue #9 · **Depends on:** `riparian/labels/csu_points.py`

## Context

Our contribution claims **defoliation is a state, not absence** — that a *Tamarix* stand browning
early because *Diorhabda* ate it must be modelled as defoliated tamarisk, not as "no tamarisk". Until
the CSU field-point crosswalk landed, that claim had **no labels at all**.

It now has 547 beetle-affected records. But counting where they *are* produced an awkward fact:

> **Zero `red tam` (defoliated) points fall inside the San Juan basin.** Our AOI contains just **4**
> `mixed` beetle-affected points. All 283 defoliated records are elsewhere.

So the model cannot be trained *and* validated on defoliation inside the AOI. Something has to give.

## The evidence that decides it

The beetle's impact in 2017 was **not uniform across the basin** — it was ecoregionally split:

| Trip | Latitude | Tamarisk live | Defoliated | Beetle-affected |
|---|---|---|---|---|
| **Escalante** (UT — Colorado Plateau) | 37.1–38.9 | 21.6% | **31.5%** | heavy (78%) |
| **SouthWest_CO** (our region) | 36.7–38.2 | 74.1% | **0%** | modest (26% mixed) |
| Arizona (Sonoran/Mojave) | 32.7–35.1 | **87.0%** | 8.5% | light |
| Virgin River (Mojave) | 36.1–37.1 | 20.8% | 62.5% | heavy |

**Arizona is a bad transfer source, and not merely because it is far away.** It is a *different
desert* (Sonoran/Mojave, 32–35°N), and it was at a *different stage of biocontrol* — 87% of its
tamarisk was still live. A model that learns "what defoliated tamarisk looks like" from Arizona is
learning it under a different climate, a different phenological calendar, and a different beetle
regime.

That is a transfer **across an ecoregion boundary**, which is precisely what the literature warns
about — and we have already written the warning down. CO-RIP reports **κ ranging 0.42–0.90 across
its 12 ecoregions**, and `docs/STATUS.md` already records the consequence:

> *"performance is ecoregion-dependent, so a single blended accuracy number for the basin is
> misleading — ours must be reported per region."*

Excluding the lower basin is therefore **principled, not convenient**. Including it would violate a
rule this project has already committed to.

## Decision

**Train the defoliation/invasives head on the ecoregion-matched Colorado Plateau pool — Escalante +
SouthWest_CO. Validate on the San Juan. Exclude Arizona and the Virgin River.**

The pool:

| | n |
|---|---|
| Colorado Plateau records | 1,096 |
| invasive (tamarisk + Russian olive) | 610 |
| **beetle-affected** | **305** — 117 defoliated · 145 mixed · 43 dead |
| San Juan validation set | 167 (49 Russian olive, 47 tamarisk, 39 native) |

Latitude 36.7–38.9 against the San Juan's 36.5–37.8 — an adjacent, overlapping band, same plateau,
same *Tamarix ramosissima*, same *Diorhabda carinulata*.

### Why not the alternatives

- **San Juan only.** Impossible: 0 defoliated points. The claim would remain untrained and untested.
- **The whole basin.** Pools two ecoregions with materially different beetle regimes and phenological
  calendars. It would inflate the training set (547 vs 305) by importing exactly the domain shift the
  model must not learn — and would breach our own per-ecoregion reporting rule.
- **Widen the project AOI to the basin.** Defensible, but it changes the project rather than the
  experiment, and it discards the San Juan-specific reference data (NMRipMap) that Stage 1 depends on.

## Consequences

- **Prevalence differs even inside the plateau, and that is the point.** Escalante was 21.6% live;
  the San Juan was 74.1% live with **0% fully defoliated**. The model must learn the **state**, not
  the base rate. This is exactly why defoliation is a condition and not a class prior — and it is a
  clean test of whether the representation generalises or merely memorises prevalence.
- **The San Juan is an out-of-sample validation set, not a held-out split.** We are testing transfer,
  and must say so. Reporting a San Juan number as if it came from the same distribution would be
  dishonest.
- **This is falsifiable.** If a plateau-trained model transfers poorly to the San Juan, that is a
  finding — and given that the San Juan sat at an *earlier* stage of beetle impact in 2017, a drop is
  a live possibility rather than a formality.
- **Label vintage 2017** applies to the whole pool: fit against 2017 imagery.
- Per-ecoregion reporting is now mandatory, not optional. A single blended number would hide the very
  effect this ADR is built around.

## Open

- **The 2017 snapshot is one year of a moving process.** The beetle front advances; Escalante-2017 may
  be where the San Juan arrives later. The temporal record (see the fine-tune ADR) is what would let
  us test that rather than assume it.
- SouthWest_CO contributes only 54 tamarisk records. The plateau pool leans heavily on Escalante, so
  "ecoregion-matched" is doing real work here and should not be overstated as "local".
