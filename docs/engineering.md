# The engineering method — specs, rules, gates, review, and what still isn't covered

The companion to [the research method](method.md). Same discipline, different failure mode: research
errors are *wrong conclusions*; engineering errors are *wrong systems*. Both are invisible when the
output looks finished, and both are fixed mechanically rather than by exhortation. See CLAUDE.md.

This document is deliberately unflattering at the end. **The gaps section is the most useful part.**

---

## Origin, and the thing it was missing

The encoding-loop method this project uses comes from the **NextAurora / NovaCraft** work — rules
encoded across five surfaces, ordered by enforcement strength, promoted down a tier as they *earn* it
([public write-up](https://www.linkedin.com/posts/joshua-dell_aiengineering-agenticai-claudecode-share-7469449311131566080-eQRL/)).
Its author names the open problem himself:

> *"improvement is observable but not yet quantified."*

**This repo is an attempt to quantify it.** Not with a controlled trial — that would need a second
team building the same system without the gates — but with **receipts**: every rule, the dated defect
it actually caught, and (crucially) the defects that *escaped the tiers where no gate existed*.

The honest bound: **N = 1 project, receipts not a randomized study.** What it can support is a much
narrower claim, and the evidence for it is unusually clean:

> **Every rule that was only *documented* drifted. Every rule that was *mechanized* held.**
>
> Zero mechanized rules drifted. Three documentation-only surfaces did — including one described as a
> live "enforcement surface" in six documents while being **invoked by nothing, ever**.

---

## The chain

**Spec → rule → gate → review → correction.** A rule that stops before "gate" is a suggestion.

### 1. Specs — `docs/specs/`, `/feature-spec`
Stage 1 (delineation), Stage 2 (invasives), Stage 3 (annual change), doc-intelligence. Each states
what is built, what is deferred, and *why*. **ADRs** (`docs/decisions/`) record decisions with the
alternatives explicitly rejected — the rejected column is the part that stops a decision being
relitigated from scratch six weeks later.

### 2. Rules — `CLAUDE.md` (canon), `CONTEXT.md` (vocabulary)
SOLID; ASP.NET Core minimal APIs with `TypedResults`; Dapper (not EF) for geo; the service/repository
split; `CancellationToken` on every async signature; EPSG:4269 storage CRS with geography casts for
distance; the medallion flow bronze→silver→gold and **never** write back upstream; peak-growing-season
imagery only; the canonical NDVI thresholds.

**Lean canon:** CLAUDE.md is capped at 500 lines (soft 400) and CI enforces it. Detail moves to a
paired doc. A canon nobody reads is not canon, and the cap is what stops it becoming one.

### 3. Gates — the only tier that actually holds

| Gate | Runs | Catches |
|---|---|---|
| `ci-python` — ruff, mypy, **47 tests** | per PR | logic, lint, types |
| `ci-dotnet` — **33 xUnit tests** | per PR | service layer, tile-SQL invariants |
| `ci-frontend` — `tsc --noEmit` | per PR | types |
| **Drift gates** — tombstones · retracted claims · doc orphans | per PR, **required** | *semantic* drift (see [method](method.md)) |
| encoding-loop — canon budget, diagram pairing | per PR, **required** | structural drift |
| **CodeQL** (C#, Python, TS) | per PR + weekly | dataflow / injection |
| **gitleaks** | per PR | committed secrets |
| **vulnerable-packages** (NuGet, pip, npm) | weekly + on manifest change | CVEs |
| SonarQube | on demand | static analysis |
| PreToolUse `block-sync-over-async` | on every AI edit | `.Result` / `.Wait()` |
| **Merge gate** — CodeRabbit review green on *this head* | before merge, **enforced by branch protection** | everything a human would miss |

### 4. Review — three independent readers
**CodeRabbit** (Tier 2, automatic, path-scoped via `.coderabbit.yaml`), the **`architecture-reviewer`**
agent (Tier 1, on demand via `/check-rules` — see the confession below), and a **multi-agent
"ultracode" review**, which produced **25 confirmed findings** (3 high) that unit tests had passed.

### 5. Correction — continuous, and recorded
Every fix lands as a PR through the merge gate. **19 PRs, every one merged through it.** Defects that
recur get *promoted a tier*: from a comment, to a rule, to a gate.

---

## Receipts — engineering defects, and what caught each

| # | Defect | Why it mattered | Caught by |
|---|---|---|---|
| 1 | `MvtTileSql` layer guard `^[a-z_]+$` | **In .NET, `$` also matches before a trailing newline** — `"wetlands\n"` passed validation and reached an interpolated SQL literal | **CodeRabbit** — CI, SonarQube, 20 unit tests and a human review all passed it |
| 2 | Every full ETL run **silently emptied** `silver.buffer_wetlands` | `analyze_buffer_wetlands()` was commented out of `run()`, and the truncation cascade removed the rows anyway | multi-agent review |
| 3 | ArcGIS returns **HTTP 200 with an error body**; the paginator read that as an empty page and **jumped the offset** | silent gaps in bronze — data that looked complete and wasn't | multi-agent review |
| 4 | LANDFIRE EVH's `32767` fill value averaged into canopy-height stats | inflated heights, feeding the health score | multi-agent review |
| 5 | `health_scorer` zipped height and lifeform from **different-length lists** | misaligned pairs — scores computed from mismatched vegetation | multi-agent review |
| 6 | Gold summary aggregated **basin-wide** instead of per watershed | every watershed reported the same number | multi-agent review |
| 7 | LiDAR CHM differenced DSM and DTM **without reprojecting to a common grid** | canopy heights off by whatever the grid offset was | multi-agent review |
| 8 | Nine tile queries had **drifted apart**; the index-backed bbox pre-filter was missing from some | 10–40× slowdowns, per-layer and invisible | refactor to one canonical `MvtTileSql.Build` |
| 9 | `max_timesteps` **floored**, so a stride kept *more* steps than requested | silently ran a different experiment than configured; later fatal | running it |
| 10 | Shipped **DEBUG colors** in the map legend | magenta "unknown" polygons in a portfolio demo | map-UI review |
| 11 | **`Request.Path` logged unsanitised** — ASP.NET Core *decodes* it, so `/foo%0AFATAL...` arrives as `"/foo\nFATAL..."` | **log forging**: an attacker writes lines into the audit trail meant to catch them | **CodeQL** (`cs/log-forging`, error) |

> **Defect 11 is the most instructive one here, because the first fix was wrong.** CodeQL flagged the
> middleware; I read it as the `X-Correlation-Id` / `X-Session-Id` headers, sanitised those, added 12
> tests, and shipped it. The headers *were* a real bug — the correlation ID is echoed into a response
> header, so it was also a response-splitting vector — **but it was not what the scanner was pointing
> at, and the alert stayed open.** The tainted value was `Request.Path` all along, in **two**
> middlewares, one of which I had never touched.
>
> **A scanner that keeps complaining after you have "fixed" something is usually right.** The
> temptation at that moment is to dismiss the alert as a false positive. It was not.

**Pattern:** defects 2–7 were all in the **Python ETL**, all data-corrupting, and all invisible to the
test suite — because they were *semantic*, not syntactic. The ETL produced numbers. The numbers were
wrong. Nothing crashed. **That is the same failure mode as the research errors, in a different costume.**

---

## The confession

**The `architecture-reviewer` agent was invoked by nothing, for the entire life of the repo** — while
being described as a live Tier-2 enforcement surface in CLAUDE.md, CONTEXT.md, the README, STATUS,
`.coderabbit.yaml`, and an ADR.

Six documents asserting a control that did not exist. It is now honestly demoted to **Tier 1** (on
demand) and actually launched by `/check-rules`.

This is the single most transferable finding in the repo, and it is why the tier table above says
**when it runs** rather than what it covers: *a surface nobody runs is documentation, not enforcement.*

---

## What is NOT covered — the honest gaps

Listing these is the point. A quality story that only lists its strengths is marketing.

| Gap | Risk | Status |
|---|---|---|
| **Frontend has no test runner at all** | `App.tsx` carries real logic — layer state, a stale-response guard, popup rendering. `tsc` proves it *type-checks*, not that it *works*. | **Open.** Needs Vitest + React Testing Library. |
| **`BannedApiAnalyzers` not wired** (build-time banned APIs) | `block-sync-over-async` is a **PreToolUse hook** — it blocks *the AI's* edits. **A human typing `.Result` in an IDE is unblocked.** The rule only binds the agent, which is precisely backwards. | **Open — needs a NuGet package**, and CLAUDE.md forbids adding one without asking. Asking. |
| **No live-DB integration test** | Every C# test mocks `IPostGisRepository`. The SQL itself — the PostGIS operators, the index pre-filter — is never executed in CI. | **Open.** Testcontainers is the fix. |
| **No coverage measurement** | 80 tests sounds like a lot. Nobody knows what fraction of the ETL they touch, and defects 2–7 suggest the answer is "not the important part". | **Open.** |
| **No performance regression gate** | The 10–40× tile speedup could silently regress; nothing would notice. | **Open.** |
| ~~**ETL has no live smoke test in CI**~~ | ~~The pipeline that produced defects 2–7 is exercised only by pure-function tests.~~ | ✅ **CLOSED.** `tests/test_etl_regressions.py` pins defects 3, 4 and 5 (11 tests, no network); a **live `postgis/postgis` service container** in CI now executes the SQL for defects 2 and 6. **Every one of the six had been *fixed* and *none* had been pinned by a test** — they could all have regressed in silence. |

**The gate went where the defects were.** The subsystem with the worst record (ETL, 6 of 10) had the
weakest gate; it now has the newest one. Two things are worth stating plainly:

1. **All six ETL defects had been fixed, and not one was pinned by a test.** Every one could have
   regressed in silence. A fix without a regression test is a fix with a shelf life.
2. **The two worst were unreachable by any mock.** Every C# test mocks `IPostGisRepository` and every
   Python test was a pure function — so **the SQL was never executed by any gate, anywhere.** A mock
   returns whatever you told it to; it cannot tell you that `TRUNCATE ... CASCADE` silently took your
   dependent table with it. That needed a real database, and now CI runs one.

   **It proved itself on its first run, at my expense.** The new live-DB test hard-coded
   `buffer_id = 1` when rebuilding after the wipe — and PostgreSQL rejected it with a
   `ForeignKeyViolation`, because `TRUNCATE` does **not** reset the `SERIAL` sequence: the rebuilt row
   lands on a fresh id. **A mock would have accepted `buffer_id = 1` without complaint.** The gate
   caught a false assumption in the very test written to demonstrate it. That is the argument for
   running the SQL for real, made better than any paragraph could.

**What this did NOT fix:** the frontend still has no test runner, there is still no coverage
measurement, and `BannedApiAnalyzers` is still unwired — deliberately, because sync-over-async has
**never once been violated** in this repo, and the method's own rule is *do not mechanize a rule that
has never been broken*. The gate budget went to the six defects that actually happened rather than the
zero that haven't.

---

## Promotion — how a rule earns a tier

The method's core idea, and the thing that keeps the canon from bloating:

1. **Tier 1 — write it down.** Cheap. Drifts.
2. **Tier 2 — put it in review** (`.coderabbit.yaml` path rules, an agent checklist). Catches most of it.
3. **Tier 3 — mechanize it.** Only when a rule has *earned it* by being broken.

The NDVI thresholds went 1 → 3 (they drifted across four files, so they are now a **tombstone**). The
CodeRabbit review went 2 → 3 (it caught a live injection, so it is now a **required branch-protection
check**). Sync-over-async is stuck at 1.5 — the hook binds the agent but not a human, which is the gap
above.

**Do not mechanize a rule that has never been broken.** You will spend the budget on ceremony and have
none left for the rule that is actually costing you.
