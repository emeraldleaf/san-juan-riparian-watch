# Corpus delta contract

**Public repo → private harness.** The contract for keeping the agents' index in step
with this repo's documents. Companion to `API_CONTRACT.md`; the operational picture is
in `docs/corpus-automation.md`.

## Why a delta

`docs/` **is** part of the RAG corpus, so an edited spec or a new retraction must reach
the index or the agent keeps answering with the superseded version — the one surface a
reader is most likely to interrogate.

A full re-ingest re-embeds every document (~30 min on the box's CPU, holding its single
self-hosted runner while deploys queue behind it). A typical docs push touches one or
two files. Re-embedding the other fifty-six to pick those up is the kind of waste that
gets automation switched off, so the sync is incremental.

Incremental sync has one hard requirement that append-only ingestion does not meet:
**it must handle deletions.** A removed document's chunks otherwise stay in the index
permanently and remain citable. `--resume`-style "skip what's already indexed" is worse
than nothing here: it never re-embeds an *edited* document, so it silently pins stale
content.

## Who computes what

The **public repo** computes the delta — it is the only side with the git history — and
the **harness** applies it. Neither guesses.

The watermark is `github.event.before`: GitHub supplies the previous commit on every
push, so there is no stored sync state to drift, corrupt, or reset.

## Payload

Sent as `client_payload` on a `repository_dispatch` with `event_type: canon-changed`.

```jsonc
{
  "mode": "delta",           // "delta" | "full" | "noop"
  "from": "<sha>",           // the watermark (github.event.before)
  "to":   "<sha>",           // the pushed commit
  "added":    ["project-2026-08-21-invasive-fm-vs-rf-loro.md"],
  "modified": ["project-STATUS.md"],
  "deleted":  ["project-old-note.md"]
}
```

Ids are **corpus ids** (`source_file` as stored in the index), not repo paths — a delete
has to target what the index actually holds. Ids are flat: `project-` + basename,
regardless of subdirectory, because the index has no notion of `docs/specs` vs
`docs/decisions`.

## Modes, and when each is used

| mode | when | the harness must |
|---|---|---|
| `delta` | normal push with a usable base commit | delete `modified ∪ deleted` by `source_file`, then re-embed `added ∪ modified` |
| `full` | no usable base (new branch, force-push, manual run), **or `seed_sources.yaml` changed** | re-fetch and re-index everything |
| `noop` | nothing indexed changed (e.g. only a diagram moved) | do nothing |

**Why a seed change escalates to `full`:** the seed list governs *external* sources, and
a git diff of `docs/` cannot see that an agency PDF was added or dropped. Escalating is
the honest response to a delta that would otherwise be silently incomplete.

## Guarantees the applier must keep

1. **Delete before write.** Chunk counts change between versions, so a document cannot
   be overwritten in place. Delete every point with that `source_file`, then insert.
2. **A rename is a delete plus an add** — the chunks live under the *old* `source_file`
   and nothing else will remove them. (A move that keeps the basename is a `noop`: the
   corpus id is unchanged.)
3. **Flush the semantic cache** after any mutation. Cached answers were generated against
   the previous corpus and would serve exactly the claim just corrected.
4. **Fail loudly, change nothing silently.** A partial apply must not report success: the
   next delta assumes everything before it landed.
5. **Additive-safe.** Re-applying the same delta must converge to the same state, since
   dispatches can be retried.

## Failure modes this exists to prevent

- **The stale retraction.** A withdrawn claim corrected everywhere except the index.
  Observed 2026-08-23: the live collection held pre-reframe copies of `STATUS.md` and
  the FM-vs-RF result.
- **The immortal document.** A deleted doc still answering questions because nothing
  ever removes vectors.
- **The silent skip.** `--resume` semantics that treat "already present" as "current".
