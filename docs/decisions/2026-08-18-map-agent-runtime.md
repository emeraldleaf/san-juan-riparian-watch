# ADR: The conversational map agent — one tool loop, two policies

**Date:** 2026-08-18
**Status:** Accepted
**Owner:** Joshua Dell (solo)
**Related:** [Conversational map agent spec](../specs/2026-08-18-conversational-map-agent.md) ·
[Document-intelligence subsystem](2026-07-04-document-intelligence-subsystem.md)

![The map agent — one loop core, two policies: the runtime flow, the resolve seam, the
core/policy split, and the actual tool payloads](../map-agent-runtime.svg)

## Context

The platform already runs one tool-using agent: the **document-intelligence agent** — a bounded,
**read-only** tool loop over the corpus (`search_corpus`, `search_filtered`, … `finish`), whose one
load-bearing security property is that *the blast radius of a fully successful prompt injection is a
bad answer*, because no tool mutates anything.

The [spec](../specs/2026-08-18-conversational-map-agent.md) adds a **second** agent — a conversational
map agent that answers spatial questions with cited numbers while the map moves. This ADR settles
*how the second agent relates to the first*, and how it stays trustworthy. The implementation lives in
the private harness (see the [private/public boundary](2026-07-04-document-intelligence-subsystem.md));
this repo holds the spec, this ADR, and the seam contract (the resolver `docintel/geo/`, the typed
`docintel/cli.py`, the `POST /api/agent/area` endpoint).

The tempting shortcut is to give the existing loop a new system prompt and a spatial tool list. It
**demos identically** — and it inherits the loop's *document-specific policy*: the loop seeds every run
with a corpus search, and on an empty finish it rescues with document retrieval. A map question has no
documents, so that inherited path is a latent wrong-answer generator. The failure is not in either
component; it lives in the **seam** between a generic loop and a document policy nobody separated.
That class of defect — two individually-correct components sharing control, with no owner for the
invariant that spans them — is the one this ADR is written to avoid.

## Decision

### 1. One loop *core*, two *policies* — not two loops, and not one bolted-on soul

Factor `run_agent_loop` into a generic **core** and a per-agent **policy**:

| Loop **core** (shared, behaviour-preserving) | Agent **policy** (per agent) |
|---|---|
| the tool-calling round trip | the soul (system prompt) |
| the token + step budget | the tool registry |
| the read-only invariant | the seed (first action) |
| the trace | the empty-result fallback |
| | what a *citation* is |

The map agent is a **second policy over the same core**. A separate loop would fork the runtime and
refute the platform claim; a bolted-on soul would silently inherit the document seed and the retrieval
fallback. The document agent passes none of the new parameters, so its path is **byte-identical** — and
its existing test suite is the regression gate: green means the live agent did not move.

*Why this is the non-obvious cost:* the shortcut is a one-line prompt swap; this is a real refactor of
the file that runs the live agent. We pay it because "one runtime, many agents" is the platform's whole
claim, and asserting it while running two divergent loops would be a lie the code tells.

### 2. Resolve, don't guess — the model chooses the constraint; a deterministic layer satisfies it

The LLM **names a place**; it never emits geometry. A deterministic PostGIS resolver
([`docintel/geo/resolver.py`](../../docintel/geo/resolver.py)) turns the phrase into a **typed
geometry**, or returns it **unresolved** — an unknown town is reported unresolved, never turned into
coordinates. The typed CLI ([`docintel/cli.py`](../../docintel/cli.py)) then runs the *actual* query.
A wrong answer here misdirects a field crew to the wrong reach, so the boundary between *choosing* a
constraint (the model's job) and *satisfying* it (a deterministic layer's job) **is** the reliability
contract of the agent. Each layer narrows what the next can get wrong.

### 3. Every tool stays read-only

The document agent's security property extends to the map agent **by construction**: `resolve` reads
PostGIS, `area` reads through the C# API, `map` is a pure encoder. No map tool mutates state. Safety
here is a **capability constraint**, not an output filter — there is nothing an injection can make the
tools *do*, so the guardrail cannot be talked past. (Contrast an output-only safety filter, which
inspects the final string but not the tool calls that produced it.)

### 4. Every number carries its provenance

`POST /api/agent/area` returns the schema the value came from — `silver.riparian_extent`,
`gold.buffer_health_score` — so the agent cites the **query that produced the number**, not merely a
document name. Metrics with no materialized table (invasive-share, change) are **rejected, not
fabricated** — "resolve, don't guess" enforced at the data layer.

### 5. Local-first, and gated

The spatial backend (C# API + PostGIS + the resolver) is **local-dev only** today, so the map agent is
built and verified against local Aspire and **gated behind its own route**. It cannot reach the
document path in production, and it does not ship to the deployed box until the spatial backend is
deployed. Local-first is not a compromise here — the backend is not deployed regardless, and iterating
locally touches the live box zero times.

### 6. The private/public boundary is preserved

The loop core, the policies, the tools, and the soul live in the **private** harness. This public repo
holds the spec, this ADR, the resolver IP, and the typed CLI. Dependency flows **private → public
only**; nothing private is published.

## Consequences

- **Positive.** The platform claim is *demonstrated*, not asserted; the document agent is *provably*
  unchanged (its tests); the read-only and citation properties hold across both agents; the seam the
  shortcut would open is closed by design.
- **Cost.** The core/policy refactor is more work than a new prompt and touches the live loop —
  mitigated by behaviour-preserving defaults and the doc-agent test gate.
- **Open.** Session-isolation depth for a public demo (per-session now; Mothership-style ephemeral
  runtime later); the gate opens when the spatial backend is deployed. The aggregate-endpoint question
  is **resolved** — one `POST /api/agent/area` (#93), not per-buffer client-side aggregation.

## Note: where does this stop being an agent?

Autonomy is the wrong axis — every production system clamps it, so it can't be the line. The test that
holds: **can you draw the control-flow graph before the run, or only after it?** The ETL DAG is
authored in advance — a pipeline. The map agent decides *per question* whether to `resolve → area →
map`, to stop and ask you to disambiguate, or to decline as out of scope — the graph is drawn at
runtime, by the model, so it is an agent. The heavy clamping here (read-only tools, typed constraints,
a step budget, a gated route) is the **deploy tax** on running an agent in a place where a wrong answer
has a cost — not evidence that it isn't one.
