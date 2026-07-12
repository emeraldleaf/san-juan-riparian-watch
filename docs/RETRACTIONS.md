# Retractions registry

Machine-readable. `.claude/scripts/check-retracted-claims.sh` reads this file in CI: **any document
that states a retracted claim must also carry that retraction's marker.** Without it, the build
fails.

This exists because a retraction that lives in one document is not a retraction. On 2026-07-12 the
`olmoearth-rf-2026-07-06` result below was withdrawn in `docs/olmoearth-vs-rf-baseline.md` — while
`docs/engineering-review.html`, the **flagship page on the public site**, went on presenting it as a
headline win/lose result for hours, defended by reasoning that had *also* been disproved. Nothing
mechanical noticed, because every existing encoding-loop check enforces file *shape* (canon size,
diagram pairing, stale refs), not claims.

## How to add a retraction

Add a row.

- **`patterns`** — one or more extended regexes, separated by **`;`**. A document matching *any* of
  them is stating the retracted claim.
- **`markers`** — one or more case-insensitive strings, separated by **`;`**. The document must
  contain *at least one* to be allowed to mention the claim (i.e. it says the retracted thing in
  order to *retract* it, the only legitimate reason to say it).

> **Markers must be SPECIFIC to their retraction — never the bare word `retract`.** A file that
> retracts claim A would otherwise get a free pass on claim B just for containing the word. That
> false negative was live for about ten minutes: STATUS.md, README.md and the hub all carried the
> "CSU produced no map" claim and sailed through, because they happened to mention "retract" for the
> *OlmoEarth* retraction. Prefer a marker that only a genuine correction would contain — the
> corrected number, the citation that disproves it.
>
> **Separate alternatives with `;`, never `|`.** This is a markdown table: `|` is the column
> separator, so a regex alternation written `a\|b` is split across columns and the rule silently
> matches nothing. That mistake was made here first time out, and the gate passed a file it should
> have failed — a broken gate is worse than no gate, because it reports "clean".

Scope: `README.md`, `CLAUDE.md`, `CONTEXT.md`, and everything under `docs/`.

<!-- RETRACTIONS:BEGIN -->
| id | patterns | markers | what was retracted |
|---|---|---|---|
| olmoearth-rf-2026-07-06 | `F1 0\.73;F1 0\.46;RF 0\.73;OlmoEarth 0\.46` | `0\.701;0\.065` | The RF-beats-OlmoEarth head-to-head (RF F1 0.73 vs OlmoEarth F1 0.46). Invalid three ways: the ground truth was ~45% wrong (#11); the model's time axis was mean-pooled away (#9); and the labels (NAIP 2020) were four years older than the imagery (S2 2024). Corrected: **RF 0.701 / OlmoEarth 0.065**. |
| olmoearth-pooling-hypothesis | `measured the harness, not the model;measuring the harness, not the model` | `hypothesis was wrong;does not explain the gap;does not explain` | The claim that mean-pooling over time *explains* the RF-vs-FM gap. Tested 2026-07-12: fixing the pooling moves OlmoEarth from F1 0.021 → 0.065, against RF's 0.701. A real defect, but **not** the cause. Do not repeat "it just measured the harness". |
| csu-produced-no-map | `but no map;Nobody has produced\s+a wall-to-wall;They were never joined;Nobody has joined them` | `Evangelista;2-epoch` | **The claim that CSU/NREL produced occurrence points "but no map", and that nobody has produced a native-vs-invasive cover+change product.** FALSE. Evangelista et al. (2018), *Mapping Native and Non-Native Riparian Vegetation in the Colorado River Watershed* (CSU/NREL + USGS + NASA DEVELOP / Walton Family Foundation) shipped a riparian-vegetation Mapbook atlas for **2006, 2016 and the change between them**, a 2016 tamarisk atlas for *select* areas, and Russian-olive maps **on the San Juan River for 2006 and 2016**. Found 2026-07-12 by `/paper-audit`. The gap is now narrower and better grounded: theirs is **2-epoch, 30 m Landsat, and beetle-confounded** — and they state Landsat *cannot* resolve the tamarisk phenological signature. Say **that**, not "nobody made a map". |
<!-- RETRACTIONS:END -->

## Why a marker, not a ban

Banning the string outright would make it impossible to *write* the retraction. The rule is
therefore: **you may state a retracted claim only in a document that also retracts it.** That is
exactly the property we want, and it is mechanically checkable.
