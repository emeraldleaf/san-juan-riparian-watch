---
description: Draft a structured feature spec — goal + acceptance + affected surfaces + auto-referenced CLAUDE.md constraints + handoff. Feeds the encoding loop.
argument-hint: <short feature description, or "pasted">
disable-model-invocation: true
---

# Feature spec

The user is starting work on a new feature. Produce a structured spec that captures the
*handoff* — goal + acceptance + affected surfaces + which CLAUDE.md rules the
implementation must respect. The spec is ephemeral (ships as a GitHub issue + PR
description, then archives); the *lessons learned during implementation* get encoded into
the durable rule set.

Pattern: spec → code → encode lessons → smarter next session.

## Inputs

`$ARGUMENTS` is one of:
- A short feature description in plain language → spec it directly
- The literal word `pasted` → the description is in the user's previous message; spec that
- Empty → ask the user what feature they want to spec

## What to do

### 1. Value gate (before drafting anything)

Answer honestly **before** drafting. If the answers don't land, this isn't a feature — it's
an experiment, and the right output is a token budget + a stop-time, not a spec.

1. **Who needs this, and what breaks for them if it never exists?** If "no one" → experiment.
2. **Would we still build it if it cost a week of engineering time instead of an afternoon
   of tokens?** Most feature inflation dies here.
3. **Who owns saying no to this?** A decision with no owner is a trap. (Solo work: you.)

Once the gate passes, lock in what the one-liner didn't say (2–4 tight scoping questions):

- Which layer(s)? — Python ETL (`python-etl/`), C# API (`RiparianPoc.Api/`), React
  frontend (`frontend/`), SQL schema (`sql/`), or Aspire orchestration (AppHost)?
- New API endpoint, new ETL step, new map layer, new schema migration — or a change to
  existing behavior?
- Which medallion schema does it read/write? (bronze → silver → gold, one direction only)
- New external data source (Planetary Computer / NWI / SSURGO / LANDFIRE / NLCD), or an
  existing one?
- New ML/model integration (OlmoEarth checkpoint, new index) or pure data processing?

Skip any question the description already answers.

### 2. Draft the structured spec

Markdown with these sections:

**Goal** — one sentence: the user-facing outcome.

> **Two-implementations test.** *"Could two completely different implementations both
> satisfy this goal?"* If yes, you wrote a goal. If only one implementation could satisfy
> it, you wrote a spec disguised as a goal and demoted the agent from decision-maker to
> typist. *"Map where riparian vegetation actually is, independent of hydrology buffers"* is
> a goal. *"Run OlmoEarth-v1-Base over 12-band S2 chips masked by NLCD class 90"* is a spec
> in goal's clothes.

**Acceptance criteria** — bullets, externally observable:
- API contract (request shape, GeoJSON/typed response shape, status codes)
- ETL side effects (which bronze/silver/gold rows written, run-tracker entry, upsert vs
  truncate)
- Spatial correctness (CRS EPSG:4269, geography cast for distance/area, GiST-indexed geom)
- Frontend behavior (layer renders, legend entry, popup fields, session header sent)
- Failure modes (invalid bufferId, empty result, upstream data source unavailable, cloud
  cover / no imagery for date range)

> **Constraints vs failure conditions.** For each line: *"Would knowing this change how the
> builder writes code?"* Yes → constraint (goes in the constraints section). No → failure
> condition (goes in acceptance; the validator catches it after the code exists). Example:
> *"Must not add a NuGet/npm/pip package without asking"* → constraint. *"NDVI health
> categories must match the calibrated thresholds"* → failure condition.

**Affects** — surfaces this touches:
- New / changed endpoints (`GeoDataEndpoints.cs` + service interface + `PostGisRepository`)
- New / changed ETL steps (`etl_pipeline.py` / processor modules / `entrypoint.py` mode)
- New / changed schema (`sql/*_migration.sql` — never edit `create_schemas.sql` per CLAUDE.md)
- New / changed map layers (`App.tsx` + component + legend)
- New external data sources or ML checkpoints
- New dependencies (flag explicitly — CLAUDE.md forbids adding without asking)

**Upstream dependencies (assumptions that could shift)** — load-bearing assumptions this
spec depends on; if any change mid-build, flag that the spec is invalidated:

- External API contracts (Planetary Computer STAC, NWI/SSURGO/LANDFIRE/NLCD endpoints,
  maxRecordCount pagination behavior)
- Imagery availability (peak growing season June–August for the San Juan Basin; cloud
  cover; S2 vs S1 vs HLS revisit)
- Schema shape (medallion tables, FK cascade chain, unique constraints for upsert)
- CRS assumptions (EPSG:4269 storage, geography casts)
- CLAUDE.md rules themselves in flux

**Non-functional constraints** (optional, only when relevant) — qualities in business
language, 5–7 lines max. ✅ "Delineation must run CPU-only on the local Mac." ✅ "ETL
incremental mode must not wipe NDVI data." ❌ "Use rasterio.mask" (that's Context/how).

**Constraints from CLAUDE.md** — auto-reference the rules that apply, pulled from the
*current* CLAUDE.md (read it; don't reconstruct from memory). Name each rule + link its
section. Common candidates for this project:

- **Spatial CRS + geography casts** — EPSG:4269 storage, `geom::geography` for distance/area,
  `ST_Buffer(geom::geography, meters)`, GiST index, `&&` bbox pre-filter
  → CLAUDE.md "Conventions → Spatial Data"
- **Medallion one-way flow** — bronze → silver → gold, never write upstream
  → CLAUDE.md "Architecture → Medallion Architecture"
- **Do-not-modify list** — `create_schemas.sql`, `azure.yaml`, AppHost `Program.cs`, CRS,
  field mappings; no new packages without asking
  → CLAUDE.md "Do Not Modify (without explicit request)"
- **Service-layer boundaries** — endpoints thin; SQL lives in services; repository is
  generic data access
  → CLAUDE.md "C# / .NET → Service Layer Architecture"
- **Async + CancellationToken** — on all I/O method signatures; `CommandDefinition` carries
  the token
  → CLAUDE.md "C# / .NET" + "Data Access (Dapper)"
- **Observability** — `ActivitySource.StartActivity` + `SetTag` on service/repo methods
  → CLAUDE.md "Observability (OpenTelemetry + Aspire)"
- **NDVI & phenology** — peak growing season only; tag `season_context`; dormant ≠ bare
  → CLAUDE.md "NDVI & Phenology"
- **Python standards** — type hints everywhere, `Protocol` interfaces, SQLAlchemy `text()`,
  frozen dataclasses, GeoPandas for PostGIS I/O
  → CLAUDE.md "Python"
- **SQL standards** — named columns (no `SELECT *`), CTEs, parameterized only, audit
  timestamps, `&&` bbox pre-filter
  → CLAUDE.md "SQL (PostgreSQL / PostGIS)"

Include only the constraints that apply to *this* feature.

> **This constraint list paraphrases CLAUDE.md rules — keep it in sync when CLAUDE.md
> changes.** The PostToolUse hook surfaces this file when CLAUDE.md is edited; `/check-rules`
> audits alignment. See CLAUDE.md.

### 3. Significance check — ADR or not?

Does this introduce or change an architectural decision worth recording?

- New external data source / new medallion table / new schema → **yes**, draft an ADR
- New ML model integration (OlmoEarth, a new foundation model) → **yes**
- Replacing a core method (e.g. hydrology-buffer delineation → learned delineation) → **yes**
- New CRUD endpoint following existing patterns → **no**
- Bug fix → **no**

If yes, draft `docs/decisions/YYYY-MM-DD-<slug>.md` (ADR-style): Context / Decision /
Alternatives considered / Consequences. If `docs/decisions/` doesn't exist, note it would
be created in this feature's PR.

### 4. Outputs

1. **GitHub issue body** — ready to paste into `gh issue create` (What / Why / Acceptance /
   Notes). Suggest labels: `type/feature`, relevant `area/*` (etl / api / frontend / sql),
   `priority/*` if known.
2. **Optional ADR draft** — if the significance check returned yes.
3. **Scaffolding suggestions** — concrete next steps after approval, per CLAUDE.md "Common
   Patterns" (adding an endpoint / ETL step / map layer). Name the canonical reference file
   to mirror.

### 5. Gap check — close the holes before shipping

> *"Hand this spec to someone not in your head — or to the AI implementing it next session.
> Where would they have to guess?"*

Walk every section; mark each place an implementer would infer rather than read. Common
holes for this project:
- Acceptance that names success but not failure modes (no imagery for date range, empty
  spatial intersection, upstream 500)
- Affects that says "the ETL" without naming the processor module + `entrypoint.py` mode
- Constraints that say "follow the spatial rules" without naming the CRS + geography cast
- Upstream deps that mention "Planetary Computer" without naming the collection + band order

Every guess-point is a hole the agent fills silently. Close them before implementation.

### 6. Closing the loop

End with this prompt to the user (verbatim):

> **This spec captures the handoff.** Once you've shipped, what did building this surface?
> Any "we should never write this again" or "we should always do this when" — encode it
> across the 5 surfaces. The spec is ephemeral; the lessons are how the loop compounds.

## Style notes

- The spec is a handoff document, not a thesis. ~1 page of markdown.
- Don't restate CLAUDE.md rules — *link* to them.
- Don't draft the implementation — the spec is "what + must-be-true," not "how."
- If the feature matches an existing pattern, name the canonical reference file (e.g.
  `ndvi_processor.py` for the clip-raster-to-buffer shape) and short-circuit.

## What this command is NOT

- **Not Spec Kit.** No plan or task list — just the structured spec.
- **Not a tutorial.** Doesn't re-explain CLAUDE.md rules — references them.
- **Not an auto-encoder.** Proposes the spec; the user decides whether to open the issue /
  draft the ADR / start scaffolding.

Run the spec on the feature identified by `$ARGUMENTS` now.
