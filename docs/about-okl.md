# The engineering method — OKL & the encoding loop

This project was built with an AI coding agent, and the interesting risk of that is **not** hallucinated
code — a compiler catches that in seconds. The dangerous failure of fast, fluent, AI-assisted work is
the kind that *compiles, passes tests, and reads beautifully* while being wrong: a **retracted result
still presented as fact**, a model **scored against 45%-wrong labels**, a **novelty claim a 2018 paper
already falsified**, a headline number that **quietly went stale** on the public page. None of those is
a syntax error. Each was a real event on this project. The method exists to catch that class of failure
mechanically, and it is itself a deliverable of the portfolio.

## OKL — a knowledge layer for AI-assisted engineering

The backbone is **OKL**: *a small database of the specific lessons a codebase has learned* — the bugs it
keeps almost-reintroducing, the checks that catch them, the rules that must not be broken — plus a
command that hands the relevant lessons to a coding agent (or a person) **before** they start a task, so
the same mistake isn't made twice.

The problem it solves is ordinary and expensive: someone fixes a subtle bug, learns *why*, writes a rule
to prevent it — and weeks later, in a different file or repo, the same class of bug returns, because
whoever did the new work never saw the rule. The knowledge existed; it just wasn't **in front of the
person who needed it, at the moment they needed it.** OKL's one move is to make the relevant lessons
**read automatically at the start of a task**, not looked up if someone remembers.

Each lesson is a small, typed note with a **Symptom → Cause → Fix** — actionable, not just
informational. The note kinds map exactly onto the guardrails this project runs:

| OKL note kind | What it captures |
|---|---|
| **Defect** | A specific mistake that happened, and why. |
| **Gate** | An automated check that catches a class of defect. |
| **Rule** | A standard to follow ("do X, never Y"). |
| **Retraction** | A claim that turned out false and was withdrawn. |
| **Tombstone** | An identifier (name, file, endpoint) retired and forbidden from returning. |
| **Decision** | A choice made deliberately, so it isn't silently reversed later. |

## The encoding loop — rules enforced by mechanical gates

In this repository those lessons are **encoded across several surfaces** (the canon file, the docs, the
review agent, the commands) and — the part that matters — **enforced by mechanical gates in CI**, so a
rule that everyone agrees with can't quietly rot. Every gate is deterministic: no model, no judgement,
the same answer on a laptop and on the CI runner.

Four **semantic** gates guard against the "compiles-but-wrong" failures that shape checks (file size,
diagram pairing, stale references) are blind to:

- **Tombstones** — CI fails any doc, comment, or config that resurrects a retired identifier. *(Born
  when retired NDVI thresholds survived a "completed" cleanup — in a docstring.)*
- **Retractions** — a withdrawn claim may appear in a document **only if that document also retracts
  it**. *(Born when a retracted result stayed live as a headline stat on the public page for hours.)*
- **Canonical results** — the **inverse**: every public doc **must carry the current value** of each
  headline result, or the build fails. *(Born when a result went stale by omission — the flagship page
  said "the test doesn't exist yet" 15 days after it had run and shipped to the front page.)*
- **Doc orphans** — every spec, ADR, and audit must be reachable from the published hub. *(Born when
  the plan-of-record was live but findable only by guessing its URL.)*

## Receipts, not slogans

The method's own claim is falsifiable, so it keeps **receipts**: a dated table of *what the project
actually got wrong* and which gate (or review) now catches it. A few, to show the shape:

- A green CI check that only meant CodeRabbit *ran* — masking a rate-limit skip where it never
  reviewed. Lesson: **a green check is not a green review.**
- A reranker that OOM-killed the box, "fixed" twice before the real fix (run it via an API) — profiled,
  not guessed. Lesson: **the cheapest fix can be deleting the code.**
- A broken gate that reported a verdict it hadn't actually computed. Lesson: **a broken gate is worse
  than no gate**, because it reports "clean."

The honest conclusion the receipts support is narrow and testable: the *documentation-only* surfaces
all drifted; only the **mechanized** gates held. That is the whole finding — encode the rule, then let a
machine, not a memory, enforce it.

*The RAG agent that answers your questions here is built on the same discipline — see
[how this agent works](about-the-agent.md).*
