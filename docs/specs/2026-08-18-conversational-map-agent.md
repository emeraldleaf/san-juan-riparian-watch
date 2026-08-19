# Spec — the Conversational Map Agent (a Shippy-shaped analysis agent)

**Date:** 2026-08-18 · **Status:** spec · **Layers:** agent runtime (Quartzose) · a typed
`riparian-cli` · the C# spatial API · the React/MapLibre frontend · evaluation.

## Why now — and the Ai2 Skylight "Shippy" precedent

Ai2's Skylight team shipped **Shippy**: *"ask a question in plain language, Shippy fuses data from
multiple sources, generates citations, and turns around maritime intelligence in minutes."* This
spec is the **riparian analog** — the same shape (a plain-language question fuses multi-source
**spatial + document** data into a **cited** natural-language answer, while the map moves to show
you) — and it **deliberately adopts Shippy's stated architecture**, because that is how the team
adjacent to this work builds agents.

Shippy's model of an agent, adopted here:
- **Soul** — the system prompt: persona + boundaries.
- **Skills** — plain markdown workflows and the scripts they call.
- **Config** — the model, plus its harness and runtime.

And Shippy's three highest-impact reliability decisions, adopted as this spec's non-negotiables:
1. **A purpose-built, typed CLI for the agent's tools** — *"agents are nondeterministic; their
   tooling shouldn't be."*
2. **Isolated sessions** — every conversation ephemeral and isolated (no cross-tenant data).
3. **Whole-agent evals** — experts write weighted rubrics, every scenario runs against live data,
   and a version that regresses does not ship.

## Goal

Let a user **ask the riparian map questions in plain language and get cited, natural-language
answers while the map moves to show them** — a second, tool-using agent on the Quartzose platform
that proves the platform generalizes beyond document Q&A.

> **Two-implementations test — passes.** The goal fixes the *outcome* (converse with the map, get
> cited answers, the map responds), not the mechanism. A ReAct loop, a plan-then-execute loop, or a
> fixed skill router could each satisfy it — so the agent, not this document, decides how.

## The load-bearing principle: resolve, don't guess

**Let the model choose the constraint; never let it satisfy the constraint.** The model picks
*which* place and *which* metric — it chooses the constraint. It never turns "Farmington" into
coordinates, and it never computes an invasive share itself. A **resolver** turns the phrase into a
**typed geometry**; the typed CLI runs the **actual query**. That step isn't retrieval, it's
**resolution** — a phrase becomes a typed constraint, and everything downstream of it is
deterministic.

Each layer narrows what the next one can get wrong: the resolver narrows the geometry so the query
can't hit the wrong area; the query narrows the value so the answer can't be fabricated. Here a wrong
answer isn't cosmetic — it points a stretched field crew at the wrong reach — so the boundary
between *choosing* a constraint (the model's job) and *satisfying* it (a deterministic layer's job)
is the reliability contract of the whole agent. It is the same instinct Skylight describes when it
resolves "Panama EEZ" to a polygon through a regions API instead of letting the model guess
coordinates, and it is *why* the two sections below exist: the typed CLI, and `resolve` as a
first-class step rather than a convenience.

## The agent, in the soul / skills / config model

**Soul** (system prompt). A San Juan riparian analyst. Boundaries: answer only from the basin's own
data — the spatial layers and the document corpus; **cite every number** to the query or source that
produced it; **decline out-of-scope** (reuse the existing LLM scope gate); never fabricate a
statistic or a geometry.

**Skills** (markdown workflows + their `riparian-cli` calls):
- `answer-area` — resolve a place → query a metric for it → move the map → answer with the number
  and its provenance.
- `find-features` — resolve a filter ("the degraded reaches") → query → highlight the matches → fit
  the map to them.
- `compare` — two areas or two metrics, side by side.

**Config**. A tool-capable model on the fast Groq path already deployed; the Quartzose agent runtime
(`app/backend/agent/tools.py`); the existing observability, guards, and semantic cache.

## The three reliability decisions

### 1. A purpose-built, typed CLI (`riparian-cli`)
The agent's tools are a **typed CLI with structured flags** — deterministic, unit-testable, and
versionable — not ad-hoc function calls. It *wraps what already exists*:

| command | returns | backed by |
|---|---|---|
| `resolve <place>` | geometry / bbox | `docintel/geo/resolver.py` |
| `area --geom <g> --metric <invasive-share\|health-grade\|extent\|change>` | value + provenance | C# spatial API |
| `find --metric <m> --op <lt\|gt> --value <v>` | matching feature geometries | C# spatial API |
| `map <fly-to\|highlight\|layer> [--bbox\|--features\|--name]` | a map action | frontend event bus |

The CLI is tested on its own — fixed inputs → fixed outputs — **independent of the nondeterministic
agent**. That separation is the point: the agent may phrase a plan a hundred ways, but each tool
call is a typed command with one behaviour.

### 2. Isolated sessions
Every conversation runs in its own session. The platform already mints a `session_id`; conversation
memory and the semantic cache are session-keyed, and each session's tool calls are scoped to public
basin data — **no conversation reads another's state**. *Scaling path (noted, not MVP):* a
Mothership-style ephemeral per-session runtime for true multi-tenant isolation.

### 3. Whole-agent evals (weighted rubrics, live data, regression-gated)
Golden scenarios scored by a **weighted rubric** against **live data**, extending the existing
`EvalService` + golden-case pattern:
- resolved the right place? · queried the right metric and got the right value? · moved the map
  correctly? · cited its number? · declined correctly when out of scope?

Each criterion carries a weight; a rubric score below threshold **fails a CI ship-gate**. This is
the existing eval framework's retrieval/routing/judge metrics, extended from "was the answer good?"
to "did the whole agent do the right things?".

## Acceptance criteria
- "How much of the corridor near Farmington is invasive?" → the map flies to Farmington, highlights
  the corridor, and the agent answers the share **with a citation to the query**, in one turn.
- "Show me the degraded reaches" → the map highlights the degraded buffers and fits to them.
- An out-of-scope question ("what's the weather?") is **declined without a spatial query**.
- `riparian-cli` passes its own unit tests (typed I/O) with the agent absent.
- The whole-agent eval runs the golden scenarios against live data, reports a **weighted** score,
  and a regression **fails the gate**.
- Traces show the tool sequence (`resolve → area → map`) for every turn.

## Affected surfaces
- **Agent runtime** (`app/backend/agent/tools.py`) — register the `riparian-cli` tools + the map
  agent's soul and skills.
- **`riparian-cli`** — new; the typed, testable, deterministic tooling layer.
- **C# spatial API** — reused as the data source; possibly 1–2 new aggregate endpoints for
  area-metric queries (prefer reusing existing per-buffer routes for the MVP).
- **Frontend** (`web/`) — extend the event bus with `story:map { action, … }`; the MapLibre map
  executes `fly-to` / `highlight` / `layer` (the bus, `story:geom` + `fitBounds`, already exists).
- **Evaluation** (`src/quartzose/evaluation/`) — weighted-rubric whole-agent scenarios + a ship gate.

## CLAUDE.md constraints to respect
- **Spatial:** EPSG:4269 storage; cast to `geography` for distance/area; `&&` bbox pre-filter before
  expensive ops.
- **Medallion, one direction:** the agent reads silver/gold; it never writes upstream.
- **Platform / deployment boundary:** the agent runtime, the CLI shape, and the eval harness
  generalize into `src/quartzose`; the riparian-specific tools, skills, and soul stay in the
  deployment (config-driven, per the deployment-framing precedent).
- **Guards + citations:** reuse QueryShield / PassageShield / AnswerScrubber and the LLM scope gate;
  every number carries provenance.
- **Sanctioned homes:** new agent/tool code lives in the agent package, not as new flat files.

## Phasing
- **Phase 1 (MVP):** `resolve` + `area` + `map:fly-to/highlight`; the `answer-area` skill; ~6
  weighted-rubric golden scenarios; traces — over the existing C# API and map.
- **Phase 2:** `find` + `compare` + layer control + change-over-time; **fuse with the document
  agent** (a number *and* a cited report); session-isolation hardening.

## Handoff / open questions
- Which model handles the tool loop best and cheapest on Groq (qwen3-32b vs a llama variant)? —
  measure, don't assume.
- Aggregate area-metric query: reuse per-buffer routes and aggregate client-side, or add one C#
  endpoint? Prefer reuse for the MVP.
- Session-isolation depth for a public demo: per-session (MVP) vs full Mothership-style ephemeral
  runtime (the scaling path).
