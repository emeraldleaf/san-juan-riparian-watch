# The corpus is a surface: keeping the agents' index honest

**2026-08-23** · paired detail for the corpus-freshness rows in the automation ledger.
See CLAUDE.md.

## Why this exists

This project's own documents — the specs, decision records, results, and
`RETRACTIONS.md` — are **in the RAG corpus** that the story-page agent and the map agent
answer from. That makes the index a *surface*, in exactly the sense the drift gates
mean: something that can quietly disagree with the repo.

The failure it creates is the worst one available here. A retraction can reach the site,
the docs, the registry, and CI, and still leave the **agent** answering with the
withdrawn claim — the one surface a reader is most likely to interrogate. That is not
hypothetical: on 2026-08-23 the live index was found to hold copies of `STATUS.md` and
the FM-vs-RF result that predated the 2026-08-21 retraction reframe, so the agent could
still narrate the "desert arroyo rescue" story that every other surface had corrected —
a story whose *attribution to arroyo morphology is unverified* (the reach is a
river-dominated subwatershed; the transfer result itself stands).

The method's own finding applies to itself: *every rule that was merely documented
eventually drifted; every rule that was mechanized held.* So re-ingest is mechanized.

## The three workflows

| workflow | repo | trigger | what it does |
|---|---|---|---|
| `notify-corpus.yml` | public | push to `main` touching `docs/**`, `CLAUDE.md`, `CONTEXT.md`, `docintel/corpus/seed_sources.yaml` | `repository_dispatch` → the harness. Skips with a **notice** (not a failure) when `CORPUS_DISPATCH_TOKEN` is unset, so a missing secret never reddens a docs push. |
| `reingest-corpus.yml` | harness | that dispatch, its own corpus-code changes, or manual | fetch (`--force`) → re-index → **flush the semantic cache** |
| `verify-corpus.yml` | harness | manual | **read-only**: collection stats + which sources are indexed |

**Setup required:** a `CORPUS_DISPATCH_TOKEN` secret on the public repo (a PAT with
`repo` scope on the harness). Without it the chain is inert but silent-by-design.

## Details that are load-bearing

- **`--force` on the fetch.** Without it an *edited* document is skipped as "already
  present" and its stale copy lives forever — precisely the drift being prevented.
- **The cache flush is not optional.** Answers cached against the old corpus would be
  served after the re-index, handing back the exact stale claim just corrected.
- **Ingest runs in the backend container, as root, from `/app`.** The box has only
  `/usr/bin/python3`; `quartzose` (the indexer) exists only inside that image; `data/`
  is bind-mounted (`../data:/app/data`) and root-owned, and the ingest resolves
  `data/raw` / `data/processed` relative to CWD.
- **Ingest is additive** (`recreate=False`, dedup on). It adds to the live collection
  rather than dropping it, so a failed run cannot leave the agents with no corpus.

## Scoped retrieval, and why it is separate from freshness

The corpus holds two different things: this project's own work, and ~30 external agency
reports and papers. Blended in one ranking they compete — *"how did **this project**
handle X"* loses to an agency paper about X, because both are about X and the paper has
more prose on it. So retrieval is scoped:

- `search_project` — our specs, decisions, results, registries (`project-*`, `audit-*`).
- `search_literature` — the outside literature only, which makes *"has anyone else done
  this?"* an honest question rather than one answerable with our own claims.

Both agents carry both tools. Implemented as a post-filter on the source prefix, not a
Qdrant filter: retrieval is hybrid (dense + sparse + RRF + rerank) and threading a
filter through every stage is a much larger change. The scoped search over-fetches 3×
and says so plainly when it still comes back thin.

## The operating rule this cost us

Twice in one session, system state was **inferred from configuration** and both
inferences were wrong: the corpus contents were read off `seed_sources.yaml` (the live
index disagreed — it had been built by a path that walks `docs/` directly), and the
box's runtime was read off its code (no `uv`, no venv, `quartzose` only in the image).
Five mutating attempts against production followed; one read-only probe settled it.

Hence `verify-corpus.yml`, and hence the rule: **look at the machine before changing
it.** Run the read-only job first — it is safe against a serving box at any time.

See also: [code-review.md](code-review.md) · [method.md](method.md) ·
[the map-agent runtime ADR](decisions/2026-08-18-map-agent-runtime.md)
