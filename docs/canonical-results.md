# Canonical results registry

Machine-readable. `.claude/scripts/check-canonical-results.sh` reads this file in CI: **every listed
document MUST contain the current value of each headline result.** A public-facing doc that omits a
current result is stale — the build fails, naming the doc.

This is the **inverse of `RETRACTIONS.md`**. That gate catches a document *stating a withdrawn claim*;
this one catches a document *missing a current one*. Both are the same disease from opposite sides — a
result living in one document while another contradicts or ignores it.

It exists because on **2026-08-16** the flagship public page `docs/engineering-review.html` still ended
section 06 with *"the fair OlmoEarth test doesn't exist yet — don't cite this as evidence about
foundation models"* — **15 days after** the leave-one-reach-out result (arroyo **0.557 → 0.889**) was
measured and put on the live site's front page. Every shape check passed. The retraction gate passed
(nothing was *contradicted*). The page was simply **stale by omission**, and nothing was looking for a
*missing* result. This gate looks.

## How to add / change a result

Add or edit a row. **When a headline number changes, change it here** — the gate then fails every
listed document until each carries the new value, which forces the docs to be updated together instead
of drifting apart. (If the old value was *withdrawn*, also add a row to `RETRACTIONS.md` so the old
number can't linger either.)

- **`value`** — an extended regex for the current value (escape the dot: `` `0\.889` ``).
- **`must-appear-in`** — one or more repo-relative file paths separated by **`;`**. Each must contain a
  match, or the build fails.

Keep this list **small and outward-facing** — the flagship page, the live-site source, the README. It
guards the *public* claims, not every internal note (internal docs are allowed to lag).

## Registry

| id | `value` | `must-appear-in` | note |
|---|---|---|---|
| fm-arroyo-fm | `0\.889` | `docs/engineering-review.html;web/src/pages/index.astro` | Fine-tuned OlmoEarth AUROC on the held-out Malpais arroyo (LORO, 2026-08-01) — the headline FM win. |
| fm-arroyo-rf | `0\.557` | `docs/engineering-review.html;web/src/pages/index.astro` | RF arroyo bar — the baseline the FM rescues; always paired with 0.889. |
