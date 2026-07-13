# The method — AI-assisted research that catches its own errors

**A companion to the science, not a footnote to it.** How this project is built is as much the
contribution as what it found. Every mechanism below exists because of a specific, dated failure it
caught — and every one of those failures is named, with receipts. See CLAUDE.md.

---

## Origin — and the gap this repo tries to close

The method comes from the **NextAurora / NovaCraft** encoding loop: rules encoded across five
surfaces, ordered by enforcement strength, promoted down a tier as they *earn* it
([public write-up](https://www.linkedin.com/posts/joshua-dell_aiengineering-agenticai-claudecode-share-7469449311131566080-eQRL/)).
Its author names the open problem himself:

> *"improvement is observable but **not yet quantified**."*

This repo is an attempt to quantify it — **not** with a controlled trial (that needs a second team
building the same system without the gates), but with **receipts**: every rule, the dated defect it
caught, and the defects that escaped the tiers where no gate existed.

**Honest bound: N = 1 project; receipts, not a randomized study.** What the evidence *does* support is
narrower and unusually clean:

> **Zero mechanized rules drifted. Three documentation-only surfaces did** — including one described as
> a live "enforcement surface" in six documents while being **invoked by nothing, ever**.

For the engineering counterpart — specs, QA, CI gates, review, and the honest list of what is still
**not** covered — see **[the engineering method](engineering.md)**.

## The thesis

> **AI-assisted research fails by producing work that is fast, fluent, plausible, and wrong — and
> the wrongness is invisible precisely because the output looks finished.**
>
> Exhortation does not fix this. Gates do.
>
> Every rule in this project that was merely *documented* eventually drifted. Every rule that was
> *mechanized* held. That is the whole finding, and it is falsifiable: the receipts below record
> which surface caught which error, and which surfaces caught nothing because nobody ran them.

The conventional worry about LLM-assisted engineering is hallucinated code. That is the *easy* failure
— a compiler or a test catches it. The dangerous failure is different:

| | Caught by | |
|---|---|---|
| Hallucinated API | the compiler | trivial |
| Wrong logic | a unit test | routine |
| **A retracted result still published as fact** | **nothing** | ← the real problem |
| **A model scored against 45%-wrong labels** | **nothing** | |
| **A novelty claim already falsified by a 2018 paper** (Evangelista et al., 2-epoch) | **nothing** | |
| **A "fix" that confirms a hypothesis that is actually false** | **nothing** | |

These are all **semantic** failures. They compile. They pass tests. They read beautifully. They are
also the ones that destroy a research result — and an LLM working at speed produces them faster than a
human can notice.

---

## What the project actually got wrong

This is not a list of things that *could* go wrong. It is what **did** go wrong, in this repo, on
these dates.

| # | The error | How wrong | Found by |
|---|---|---|---|
| 1 | `fetch_nmripmap` rasterized **every** polygon as riparian | **~45% of positive labels were wrong** — urban, agriculture, upland and water taught as riparian | multi-agent code review |
| 2 | The published RF-vs-OlmoEarth result | **retracted** — invalid three separate ways | re-derivation |
| 3 | Labels were **NAIP 2020**; we fit them against **Sentinel-2 2024** | 4-year gap = label noise we inflicted on ourselves | reading the source metadata |
| 4 | *"Mean-pooling explains the gap"* — the hypothesis the whole re-run was built on | **tested and DISPROVED.** F1 0.021 → 0.065 vs RF's 0.701 | running the control |
| 5 | *"CSU produced points but no map; nobody has done this"* | **false.** **Evangelista et al. (2018)** shipped **2-epoch** (2006/2016) change maps, incl. Russian olive **on the San Juan** | `/paper-audit` |
| 6 | *"We built an RF riparian classifier"* as a contribution | CO-RIP did it basin-wide at **κ 0.80 in 2018** | reading, **after we'd built it** |
| 7 | `MvtTileSql` layer guard `^[a-z_]+$` | **.NET `$` matches before a trailing newline** — `"wetlands\n"` reached the SQL literal | **CodeRabbit** |
| 8 | The public engineering-review page | still presenting the **retracted** result as a headline stat, defended by reasoning **also** disproved | the retraction gate |
| 9 | `/add-map-layer` — the command that *scaffolds map layers* | still said "React/**Leaflet**" — would generate Leaflet into a MapLibre app | the tombstone gate |
| 10 | `architecture-reviewer` — a documented Tier-2 "enforcement surface" | **invoked by nothing, ever.** Six documents described it as live | asking whether it ran |
| 11 | A sanity probe returned **AUC 0.23** — apparently a broken encoder | it wasn't. **Unshuffled KFold** on a spatial grid. Shuffled: **0.85** | refusing to accept a convenient bad number |
| 12 | The `Virgin_River` rows in a public dataset | **x/y transposed** — 119 points in the wrong hemisphere | counting before trusting |
| 13 | The merge gate itself, **again** — it demanded a CodeRabbit *check-run* | CodeRabbit posts **none** for an on-demand review, so the gate blocked four already-reviewed PRs **forever**. It was also *too weak*: a check-run proves it RAN, never *which commit it read* | judging by the commit CodeRabbit's walkthrough **names** |
| 14 | The OlmoEarth scaffold's `class_path`s — and the spec **asserting they were "correct"** | **5 of 23 did not exist.** Every class *name* right, every *module* path wrong; written from a plausible memory of the layout and **never once imported**. They fail at runner startup — i.e. **Phase 1, on a rented GPU** | `check-scaffold-classpaths.sh` — importing all 23, mechanically |

**Note errors 2, 3, 4 and 6.** Each was found *after* work had been built on top of it. Errors 5 and 6
narrowed the project's central novelty claim. **Error 4 disproved the very hypothesis the fix was
designed to confirm** — and was reported anyway. That is the behaviour the method is for.

---

## The two kinds of drift

The encoding loop this project inherited (from the NextAurora method) enforced **file shape**:

| Existing check | Catches |
|---|---|
| lean-canon | CLAUDE.md over 500 lines |
| doc-diagram-pairing | `.excalidraw` without a sibling `.svg` |
| check-claude-md-refs | paraphrases flagged when canon changes |
| check-file-moves | `git mv` leaving dangling references |

Not one of them could catch errors 5, 8, or 9 — because those are **semantic drift**: a document
asserting something that is *no longer true*. Structural gates are blind to it, and it is the exact
failure mode of fast, fluent, AI-assisted work.

So the loop was extended with three **semantic** gates, all mechanical, all in CI, all **required** on
`main`:

### 1. Retraction registry — `docs/RETRACTIONS.md`
A withdrawn claim is registered as a pattern. **CI then fails any document that states it without
retracting it.** Not a ban — a ban would make it impossible to *write* the retraction. The rule is:
*you may state a retracted claim only in a document that also retracts it.*

> **Why it exists:** the RF-vs-OlmoEarth result was retracted in one document while the **flagship page
> on the public site** went on presenting it as a headline win/lose stat — defended by reasoning that
> had *also* been disproved. Every mechanical check passed. **A retraction that lives in one document
> is not a retraction.**

### 2. Tombstones — `.claude/tombstones.txt`
Retired identifiers. CI fails any doc, comment or config resurrecting one. Ported from NovaCraft,
whose own rationale is exact: *"the compiler catches stale identifiers in code; NOTHING catches them in
docs, comments, and config."*

> **Why it exists:** the retired NDVI thresholds survived a "completed" reconciliation sweep — in a
> component docstring. And tombstoning `leaflet` immediately surfaced that the **command which
> scaffolds new map layers** still said "Leaflet". *A human sweep updates the docs it remembers; a gate
> updates the ones it finds.*

### 3. Doc orphans — reachability
Every spec, ADR and audit must be linked from the published hub.

> **Why it exists:** the **plan of record** — the fine-tune ADR — was live on the site and reachable
> only by guessing its URL.

---

## Adversarial practices

Gates catch drift. These are for catching *being wrong*.

### `/paper-audit` — attack your own novelty claim
A project's contribution is a claim about the literature, so **a single paper can falsify it**. This
command audits a paper against every encoding surface and can return **THREAT** — *this does what we
claim nobody has done.*

It is written to look for reasons the paper **refutes** us, not reasons it is compatible. On its first
real use it falsified Novelty Claim 1 (error 5). Records live in **[`docs/audits/`](audits/)** — the
**falsification log**, which is the related-work section of any publication from this project, written
to attack the contribution rather than justify it.

**Three of our claims have been narrowed or withdrawn by prior art. Two of them after we had already
built on them.** That is uncomfortable to publish, and it is the reason the remaining claim is worth
believing.

### The control experiment
Before spending a GPU on the interesting question, run the boring one where **we already know what
good looks like**. A bad number on the interesting question is otherwise uninterpretable — broken
pipeline, too few labels, and a real scientific effect all predict the same failure.

> **Why it exists:** the original OlmoEarth "negative result" had *four* live explanations and no way
> to separate them. See the [fine-tune ADR](decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md).

### Report the result that came out
Error 4 is the load-bearing example. The mean-pooling defect was **real** — and fixing it moved the
model from F1 0.021 to 0.065, against a baseline of 0.701. **The hypothesis was wrong.** It was
published as wrong, in the same document that had argued for it.

*A defect being real does not make it the cause.* The satisfying story is the one to distrust.

### The merge gate
`main` is protected; **CodeRabbit's *review* must be green on the PR's current head** — not merely its
*check*, which only means the reviewer *ran*, and can be stale against the commit you are about to
merge. **A reviewer that never saw your last push has not reviewed your PR.**

> **Why it exists:** CodeRabbit caught error 7 — a live SQL-injection weakening that CI, SonarQube, 20
> unit tests and a careful human review all passed.

---

## What did not work — and this is the finding

**Documentation-only surfaces drifted, without exception.**

The `architecture-reviewer` agent (error 10) was described as a live Tier-2 enforcement surface in
**six** documents — CLAUDE.md, CONTEXT.md, the README, STATUS, `.coderabbit.yaml`, and an ADR — and was
**invoked by nothing, for the entire life of the repo**. It is now honestly demoted to Tier 1
(on-demand) and actually launched by `/check-rules`.

**A surface nobody runs is documentation, not enforcement.** Writing the rule down felt like
compliance. It wasn't. This is the single most transferable lesson here, and it is *why* the gates are
mechanical rather than exhortative.

**And a broken gate is worse than no gate**, because it reports "clean". The worst example is the
merge gate itself:

> ### 🔴 The merge gate was theatre for 25 of 29 merged PRs
>
> `.coderabbit.yaml` required a `coderabbit` **label** for auto-review. Without it CodeRabbit
> **skips** the PR — **and still posts a SUCCESS check.** The gate trusted that check and then counted
> inline comments; a skipped review has **zero** comments, so it printed **"✓ no CodeRabbit findings"**
> and waved the PR straight through.
>
> **Absence of findings and absence of a review are indistinguishable from the outside.** That is the
> whole bug, in one sentence.
>
> **Only 4 of the first 29 merged PRs were ever actually reviewed.** Every one of the other 25 passed
> this gate. It bought confidence that nothing had earned — while I was writing documents about how
> gates beat exhortation.
>
> A **mandatory** merge gate and an **opt-in** reviewer are a contradiction, and the reviewer wins it
> silently. Fixed on both sides: the label filter is gone, and the gate now demands **positive evidence
> of a review on the current head** and fails outright on a "Review skipped" notice.
>
> Found because a reviewer asked a question I could not answer without checking.

Other gates that reported "clean" while broken:

- The retractions registry is a **markdown table**, so `|` is the column separator — and a regex
  alternation written `a\|b` **split across columns**. The gate matched nothing and reported success.
- A **generic marker** (`retract`) let a file that retracted claim *A* get a free pass on claim *B*.
  STATUS.md, the README and the hub all sailed through while carrying a false claim.
- `mapfile` doesn't exist in macOS bash 3.2 — a gate that doesn't run identically on a laptop and in CI
  is not a gate.
- **A third kind of semantic drift the gates do not catch: *stale open items*.**
  `docs/data-licenses.md` listed "the repository has no LICENSE file" as 🔴 **open** — for hours after
  the LICENSE had been added and merged. Nobody noticed, **including me**, until a reader asked
  whether the open items were still open.
  The registries catch *retracted claims*, *retired identifiers* and *unreachable docs*. They do not
  catch **"a document says something is unresolved when it has been resolved."** And this is the
  *flattering* kind of drift — it makes the project look like it has **more** open problems than it
  does, so nothing about it feels wrong, and no instinct fires. **The drift you notice is the drift
  that embarrasses you.**
- **The gates only scanned *tracked* files.** `git grep` and `git ls-files` do not see a brand-new
  file, so a gate could pass on a laptop and fail in CI — which is exactly what happened **on the pull
  request that added this very document**. The gate refused to merge it, correctly, and in doing so
  exposed itself. Now `--untracked` / `--others`, and verified against an untracked violating file.

All three were found by **using** the gate on a real correction rather than admiring it. **Every gate
in this repo was verified to FAIL against the real drifted files from git history** — not against a
simulation.

---

## The shape of it

| Tier | Surface | Runs |
|---|---|---|
| 1 | CLAUDE.md, CONTEXT.md, `.claude/` commands, `architecture-reviewer` | when a human invokes it |
| 2 | CodeRabbit; PreToolUse/PostToolUse hooks | automatically, per PR / per edit |
| 3 | CI: tests, SonarQube, **drift gates** (`./dev.sh --check-encoding`) | automatically, **required to merge** |

*Promote a rule down a tier as it earns it.* A rule that keeps being broken belongs in Tier 3, not in a
sterner paragraph.

**Current state:** 10 enforcement scripts · 3 semantic registries (3 retractions, 6 tombstones, 3
audits) · 4 required checks on `main` · 80 tests (47 Python, 33 C#) · 19 PRs, every one merged through
the gate.

---

## Reproducing this

1. **Write the canon** (`CLAUDE.md`) and keep it lean — detail moves to paired docs.
2. **Mechanize every rule you actually care about.** If it is not in CI, assume it will drift; it will.
3. **Registries, not memory.** When you retire a value or withdraw a claim, *register* it — then let CI
   find every document that still contradicts you. It will find ones you forgot.
4. **Verify each gate by making it fail** on the real historical drift. A gate you have only seen pass
   is a gate you have not tested.
5. **Audit the literature adversarially, before you build.** A novelty claim is falsifiable; go try.
6. **Run the control before the experiment**, or a bad result will be uninterpretable.
7. **Publish the result that came out** — especially when it disproves your own hypothesis. That is the
   only thing that makes the rest of it credible.

The honest summary: **this project has been wrong in public a dozen times, and the method is what
turned each of those into a correction rather than a published mistake.**
