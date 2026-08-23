# ADR: move dense embeddings to an API, keep sparse local

**2026-08-23 · status: proposed**

> ⚠️ **Corrected twice on 2026-08-23. The original reasoning was wrong; the decision survives.**
>
> This ADR was written from "a full re-ingest never finishes" and blamed the local embedder. The
> first cause found was different: the box could not import a PDF library, so every PDF was
> byte-decoded into a multi-megabyte pseudo-document and the run was embedding **~20,000 chunks of
> binary noise instead of ~1,000 chunks of text**. Two further bugs hid HTML and mislabelled 21
> markdown files. All are fixed.
>
> **Then it was measured properly, and the conclusion here holds after all.** With extraction
> repaired the box reached **55 documents** (up from 21) and still could not embed them:
>
> | attempt | documents | embeddings done | died at | error |
> |---|---:|---:|---:|---|
> | 1 | 21 | 1 batch / 30.1 s | 31 min | none |
> | 2 | 21 | 1 batch / 30.1 s | 31 min | none |
> | 3 (extraction fixed) | **55** | 1 batch / 29.5 s | **45 min** | none |
>
> One batch in ~30 s, then silence, then a death with no traceback — the signature of an OOM kill.
> Three times, unchanged by fixing the input. **So the local embedder genuinely cannot rebuild this
> corpus on this hardware, and that is now measured rather than assumed.**
>
> One caveat before accepting: a **proven** alternative already exists — `deploy/push-to-prod.sh
> corpus` extracts locally and ships the processed JSONL, so the box never embeds a cold corpus from
> scratch. That path built the 988-point index this collection used to hold. Weigh this ADR against
> keeping that, not against the failing path.
>
> Post-mortem: [when a missing library became a 65 MB document](../2026-08-23-corpus-extraction-failure.md).

## Context

A full re-ingest embeds ~58 documents through **Snowflake Arctic Embed v2 running in Ollama**
on an 8 GB box that is simultaneously serving Qdrant, Postgres, Redis, the backend, and an
LLM. Observed 2026-08-23: the first batch reported `0/2 [02:18<?, ?it/s]` and the run did not
finish in 30 minutes.

That observation was real, but **the inference first drawn from it was wrong** — the corpus in
hand was 65 MB of undecoded PDF, not a normal corpus. Extraction has since been repaired, and the
measurement was then taken properly (see the correction above): with **55 correctly extracted
documents**, the box completed one embedding batch in ~30 s and was killed with no traceback at 45
minutes, the same signature as the two earlier runs. Fixing the input changed the document count
and nothing else.

So the constraint is real and now measured.

That is a real constraint, not an annoyance. It means:

- **there is no working recovery path.** "Re-index everything" is the standard answer to
  a corrupted or drifted index, and here it does not terminate;
- **the delta design assumes a rebuild exists.** `CORPUS_DELTA_CONTRACT.md` escalates to
  `mode: full` whenever a delta would be incomplete — an escape hatch that currently
  goes nowhere;
- **incremental sync becomes load-bearing rather than an optimisation**, which is a
  fragile place to be.

This project has already made this decision once, one component over: the reranker was a
per-query local ONNX model that OOM'd the backend, and moving it to an API took the
service from **4 GB to 218 MB**. Same shape of problem, same shape of answer.

## Decision

Move the **dense** embedder to **Voyage `voyage-4-lite`** (API, 1024-d). Keep the
**sparse** leg exactly as it is.

Hybrid retrieval is unaffected in structure, because only one leg changes:

| leg | today | after | why |
|---|---|---|---|
| dense | Arctic Embed v2 (Ollama, local) | **voyage-4-lite (API)** | removes the local model that cannot keep up |
| sparse | `Qdrant/bm25` via FastEmbed | **unchanged** | BM25 is *lexical*, not neural — no weights, negligible memory, and independent of the dense vector |

RRF fusion, the CRAG grader, and the reranker are all untouched.

`voyage-4-lite` is chosen over `openai/text-embedding-3-small` because it is **1024-d,
matching the collection's existing width**, has a 32k context (our chunks are large), and
the project already has a Voyage credential path from the reranker migration.

## The migration is a rebuild, not a flag

**Dimension match is not vector compatibility.** Arctic and Voyage vectors are both
1024-wide and occupy *different spaces*. A query embedded with one cannot meaningfully
match documents embedded with the other — and this does not raise an error. It silently
returns plausible-looking, wrong rankings, which is the worst failure mode available and
exactly the class this project treats as serious.

So: never mutate the live collection into a mixed state.

1. **Build a new collection** (`riparian_watershed_voyage`) from `data/raw/`, dense via
   the API, sparse as today.
2. **Verify side-by-side** before any cutover, with the read-only job: point count in the
   expected range, our own documents present, and a fixed question set answered against
   *both* collections with the results compared by hand. A wrong-space migration shows up
   as answers that are fluent and off-topic — you have to read them, not just count them.
3. **Cut over** by pointing `QDRANT_COLLECTION` at the new one, and keep the old
   collection until the new one has served real traffic.
4. **Roll back** by pointing the variable back. The old collection is the rollback.

## Consequences

**Gained:** a rebuild path that terminates; one less local model on a box that cannot
afford it; full re-index measured in minutes of API calls rather than hours of contended
CPU; `mode: full` in the delta contract stops being a dead end.

**Cost:** every ingest *and every query* now needs the embedding API. Retrieval acquires
a hard external dependency in its hot path — if Voyage is down, retrieval is down (today
it degrades to whatever Ollama can manage). Per-query embedding cost is small but
recurring, and it joins the existing per-query LLM + rerank spend under the same cap.

**Also true:** this makes the stack *less* self-hosted. That is a genuine loss for a
project that values being reproducible from open parts, and it is the strongest argument
against. The counter is that the local option is not currently working, and an honest
dependency beats a component that cannot complete its job.

**Not addressed here:** query-time embedding latency under the existing rate limits, and
whether the free/paid Voyage tier covers expected traffic. Measure before cutover.

See also: [corpus-automation.md](../corpus-automation.md) ·
[CORPUS_DELTA_CONTRACT.md](../../docintel/CORPUS_DELTA_CONTRACT.md) ·
[model & inference hosting](2026-07-11-model-and-inference-hosting.md)
