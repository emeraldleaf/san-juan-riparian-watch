---
name: site-prose
description: The voice and prose rules for all public-facing text (web/src pages, Chat canned answers, map-presentation narration, docs/*.html hub pages). Use whenever writing or editing anything a site visitor reads, so the voice stays consistent and the scientific rigor stays intact.
---

# Site prose: human-readable without watering down the rigor

The public site is a portfolio piece read by non-specialists and by expert reviewers at the same
time. The voice that serves both: **written like a field notebook, argued like a paper.** Story
first, number immediately after, caveat attached to the claim it qualifies. These rules were set
2026-08-22 after a full prose pass; follow them for every user-facing sentence.

## Where this applies

- `web/src/pages/*.astro` (all pages)
- `web/src/components/Chat.tsx` (SUGGEST questions, FALLBACK canned answers, greeting)
- `web/src/scripts/map-agent-client.ts` (the `PRESENTATION` narration strings)
- `docs/*.html` (the published GitHub-Pages hub)

Code comments are exempt. Footer legal/attribution separator lines are exempt.

## Voice

- **First person singular.** "I expected the classifier to flip. It didn't." Never the false-plural
  "we" for the author. The one exception: the map presentation narrator may use inclusive tour-guide
  "we" ("let's fly in", "the reach we opened on") because it means narrator-plus-viewer.
- Address the reader as "you" freely.
- Verbs over noun-piles. "The numbers change depending on how the imagery is assembled," not
  "the estimates exhibit compositing-recipe sensitivity."

## Sentences

- **No em or en dashes in prose.** Use a period, a colon, a comma, or parentheses instead. If a
  sentence needs a dash to survive, split it. (Numeric ranges use "to": "0.85 to 0.90".)
- One idea per paragraph. If a paragraph carries three ideas, it is three paragraphs.
- Never stack appositives: "the control, Russian olive, which the beetle doesn't touch, moved" is
  three clauses deep. Split it: "Before the run I declared a control: Russian olive, a plant the
  beetle doesn't touch. It moved seven times more than the signal."
- Bold sparingly: the claim, not the connective tissue.

## Jargon: introduce once in plain words, then use freely

Every technical term gets one plain-speech introduction on first use per page. Canonical
translations (use these, don't invent new ones):

| term | say instead / introduce as |
|---|---|
| phenology | "seasonal rhythm" or "timing"; then name it: "ecologists call this phenology" |
| AUC / AUROC | define at first use: "1.0 is a perfect classifier, 0.5 is a coin flip" |
| out-of-distribution | "unfamiliar ground" / "a reach unlike its training data" |
| in-distribution | "familiar reaches" / "reaches that resemble the training set" |
| leave-one-reach-out (LORO) | "train on three reaches, test on a held-out fourth, taking turns" |
| in-sample calibration | "a model agreeing with its teacher, not passing an exam" |
| compositing recipe | "how the imagery is assembled" |
| median mosaic / composite | "a cloud-free monthly image" |
| morphology | "terrain" or "landscape" |
| corridor-masked | "corridor-limited" / "within the corridor" |
| prevalence-invariant | drop it; say "gives no credit for guessing the majority" |
| spatial CV | "tested on whole stretches of river the model never saw" |
| Landsat-5 TM / sensor era | "an older satellite whose sensor is too different to reconcile" |
| per-pixel | "pixel by pixel, with no sense of its surroundings" |
| NDVI | "the standard greenness index (NDVI)" |

Numbers, units, and metric names stay exact. Translate the wrapping, never the measurement.

## Rigor rules (non-negotiable)

- Never soften or drop a number, a hedge, or a caveat. Rewrite the sentence around it.
- **Caveat travels with its claim.** No pooling disclaimers at the top of a page beyond the two
  standing hero notes (independence, proof-of-concept), which stay short.
- **Corrections come after the finding, not before.** State the corrected result plainly first,
  then a compact "this result survived its own audit" note with links. A reader must never meet a
  retraction before the claim it corrects.
- Calibrated verbs only: "well calibrated", "documented negative", "cannot resolve". Never
  "validated", "proven", "breakthrough".
- **Retraction markers must survive edits.** CI (`check-retracted-claims.sh`) requires specific
  marker phrases wherever a retracted claim is stated. Currently load-bearing on the site and hub:
  "attribution to arroyo morphology is unverified" and "river-dominated subwatershed". Check
  `docs/RETRACTIONS.md` for the current registry before rewording any correction text.
- Canonical headline numbers (`docs/canonical-results.md`) must keep appearing verbatim where
  `check-canonical-results.sh` expects them.

## Structure of a finding section

1. One-sentence transition from the previous section (each section answers a question the last
   one raised).
2. The finding in plain speech, with its number in the same breath.
3. The evidence (figure, table, map).
4. The caveat or audit note, compact, with links to the full trail.

## Before committing prose

```bash
# ALL declared prose surfaces, and BOTH dash characters (em — and en –).
# Code comments and the footer legal line are the only exempt hits.
SURFACES="web/src/pages/*.astro web/src/components/Chat.tsx web/src/scripts/map-agent-client.ts"
grep -n "[—–]" $SURFACES | grep -vE "© 2026|^\s*//|<!--"
# author-we (inclusive tour-guide "we" in the PRESENTATION narration is the one exception)
grep -nE "\b[Ww]e\b|\b[Oo]ur\b" $SURFACES
# jargon spot-check (the translation table above)
grep -niE "out-of-distribution|in-distribution|in-sample|prevalence|morpholog|compositing recipe|per-pixel|corridor-masked" $SURFACES
# cross-page consistency: statements about OLMo availability must agree everywhere
grep -rniE "olmo.{0,60}(serve|select|available)" web/src/pages/ web/src/components/Chat.tsx
# then: the build and the drift gates
cd web && npm run build
./dev.sh --check-encoding   # or run .claude/scripts/check-*.sh individually
```

Sync rule: when site prose changes meaning (not just wording), update the Chat.tsx canned answers
and the presentation narration in the same commit, so the site and the agent never tell different
stories.
