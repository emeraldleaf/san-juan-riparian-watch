# Spec: CAG vs CRAG on the project canon — pre-registered

**2026-08-22 · status: proposed (not yet run)**

## The question

Retrieval is this project's default because it was the default when the stack was
written. Context windows grew and prompt caching arrived; the constraint moved, and we
never re-tested the choice. So: **on the project's own canon, does caching the whole
corpus in context beat graded retrieval?**

Not "RAG or CAG" as an architecture religion. One measurable question, on one source.

## Why only the canon

Measured 2026-08-22:

| corpus | size | verdict |
|---|---|---|
| **project canon** (`docs/**.md`, `CLAUDE.md`, `CONTEXT.md`) | **~158k tokens** | fits a 200k window; static between commits; **the contender** |
| external literature (37 seeded agency PDFs + papers) | millions of tokens | does not fit. Retrieval, settled |

So this is a **per-source** decision, and only one source is in question. The external
literature stays on RAG + CRAG regardless of the outcome.

Note the distinction that makes this precise:

- **CRAG** (what we run today): retrieve → *grade* the results → decompose and
  re-retrieve when coverage is thin. Still retrieval; the grader raises the recall
  ceiling but does not remove it.
- **CAG** (the contender): no retrieval. Whole canon in context, KV cached, reused
  across queries. Its defining property is **cache reuse**, not merely a big context.
- **Full-context reading** (neither): loading one fresh document per task, e.g.
  `/paper-audit`. No reuse, so no cache benefit — do not call this CAG.

## Prerequisite: there is no "canon path" today

Checked 2026-08-22, and it changes the work. `search_corpus` retrieves from **one
blended collection** — project canon *and* the 37 external PDFs, unfiltered — and
**both** agents call that same tool. So neither agent is canon-only, and there is no
canon path to switch.

That means CAG cannot simply be swapped in. It requires splitting the source first:

- **the canon** → cached context (static, fits, reused);
- **the literature** → a retrieval tool (large, must stay ranked);
- the agent **chooses**, which is what a tool-calling agent is for.

Both agents would get the same two sources and the same choice — this is a change to
how a *source* is served, not a per-agent architecture.

The split is worth measuring on its own, independent of CAG, because blending has a
cost we currently absorb silently: **a method question competes in one ranking against
similarly-worded agency prose**, so "how did this project handle X" can be outranked by
a PDF paragraph about X. Splitting removes that competition even if the canon then
stays on retrieval.

The naive alternative — prefill the canon on every query — is rejected: it pays 158k
tokens for questions a PDF answers.

## Hypotheses, stated before the run

1. **CAG wins on recall.** No retrieval step means no retrieval miss — the failure mode
   where the passage exists and never reaches the model.
2. **CAG loses on cost at this traffic.** Prompt caching amortises over queries; this is
   a rate-limited public demo with sporadic traffic, so many queries land on a **cold
   cache** and pay full prefill on ~158k tokens. CAG's economics improve with load, and
   ours are the opposite shape.
3. **CAG is weaker on provenance.** RAG's citation is *structural* (retrieval selected
   the chunk). CAG's is *self-reported* (the model says where it looked). For a project
   whose rule is "no source, no claim", that is a real regression, not a detail.
4. **CAG may introduce an attention miss.** The passage is present but unused — a
   failure with no metric, unlike recall@k. Watch for confident wrong answers whose
   evidence was in the prompt.

## Method

- **Question set (n ≥ 30), fixed before the run**, drawn from real use:
  method questions the map agent now serves (`search_corpus` path), the story chat's
  canned-answer topics, and the "what did this project get wrong" class. Include
  **known-hard** ones: multi-hop (a claim in a spec + its retraction in the registry),
  and **absence** questions ("is there a validated invasive number?" — the answer is no).
- **Both arms answer the same questions**, same generation model, same temperature.
- **Score blind**: answers shuffled and graded without knowing the arm.

| metric | why |
|---|---|
| correctness (graded) | the headline |
| **citation validity** — does the cited doc actually contain the claim? | catches self-reported provenance |
| retrieval/attention miss — evidence existed, answer wrong | the failure each arm owns |
| p50 / p95 latency | prefill vs retrieval, end to end |
| **cost per query, cold and warm cache** | the economics that decide it |

## Decision rule (pre-registered)

Switch the **canon path** to CAG only if it wins correctness **and** citation validity,
with cost per query at realistic (mostly-cold) traffic no worse than ~2× CRAG. A
correctness win bought with unverifiable citations is **not** a win for this project.
If the arms tie, keep CRAG: it is built, instrumented, and already honest about misses.

Whatever the result, record it — including "we tested the default and kept it", which is
the outcome nobody publishes and everyone needs.

## Threats to this being a fair test

- **The canon is what the gates already police.** Its consistency is unusually high, so
  results may not transfer to a messier corpus. Say so in the write-up.
- **n ≥ 30 on a bounded corpus is a small sample.** Report the spread, and do not claim
  significance we cannot support (see the reach-block bootstrap: a clean point estimate
  with an interval spanning zero).
- **The grader is an LLM.** Use a different model than the one generating, and spot-check
  a sample by hand.

See also: [the map agent runtime ADR](../decisions/2026-08-18-map-agent-runtime.md) ·
[the FM-vs-RF LORO](../2026-08-01-fm-vs-rf-loro-result.md) (the house pattern for a
pre-registered comparison).
