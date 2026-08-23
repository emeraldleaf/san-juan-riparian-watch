# ADR: move dense embeddings to an API, keep sparse local

**2026-08-23 · status: proposed**

> ⚠️ **Corrected three times on 2026-08-23. The original argument is now dead; a different one survives.**
>
> **What this ADR first claimed:** a full re-ingest "does not finish" because the local
> embedder cannot keep up. **That is false, and was false when written.** The box could not
> import a PDF library, so every PDF was byte-decoded into a multi-megabyte pseudo-document
> and the run was embedding ~20,000 chunks of binary noise. Two further bugs hid HTML and
> mislabelled 21 markdown files. All are fixed.
>
> **The real cause of the failure was batch size, not throughput.** `--batch-size` counts
> **documents**, not chunks, and one corpus document is 504k characters. At the default of 10
> the box was OOM-killed with no traceback, three times, at 31/31/45 minutes.
>
> **Measured with that corrected:** at `--batch-size 1` the rebuild runs at **8.7 points/min**
> with memory flat at ~3.08 GB, and completes a full corpus in **~1.7 hours**. It terminates.
> So *"there is no working recovery path"* below is no longer true, and neither is
> *"`mode: full` goes nowhere"*.
>
> **What still argues for this ADR:**
> - **Memory, not speed.** Ollama pins **2.7 GB of a 7.7 GB box** to keep the embedder
>   resident. Moving dense embedding off-box returns that, which matters more than the hours.
> - A 1.7-hour rebuild is tolerable for a *rare* operation but painful for a frequent one.
>
> **What argues against it, and is not stated below:**
> - **It is all-or-nothing.** Query and document embeddings must occupy the same vector
>   space, so this cannot be adopted for ingest while keeping Arctic for queries. It puts an
>   external API in the **retrieval hot path**: today a slow Ollama degrades retrieval, but a
>   down Voyage stops it.
> - **Full rebuilds are rare by design.** The delta path (`sync_corpus.py`) syncs a normal
>   docs push in minutes. Adding a hot-path dependency to speed up the recovery case is the
>   wrong trade while the recovery case works.
> - **Cost is not a factor either way.** The corpus is ~448k tokens per full rebuild and a
>   query embeds 15-30. Decide this on operations, not price.
>
> **A cheaper fix addresses most of it.** `co-san-juan-dolores-planning-model-manual.pdf` is
> 504k chars — 22% of the corpus alone — and is the single reason `--batch-size 1` is
> mandatory. Splitting it at fetch time relaxes the constraint for everything else.
>
> **Status: hold.** Revisit when rebuilds stop being rare, when query latency from local
> Arctic becomes the felt bottleneck, or when the box needs Ollama's 2.7 GB back.
> Post-mortem: [when a missing library became a 65 MB document](../2026-08-23-corpus-extraction-failure.md).

## Context

A full re-ingest embeds ~58 documents through **Snowflake Arctic Embed v2 running in Ollama**
on an 8 GB box that is simultaneously serving Qdrant, Postgres, Redis, the backend, and an
LLM. Observed 2026-08-23: the first batch reported `0/2 [02:18<?, ?it/s]` and the run did not
finish in 30 minutes.

That observation was real, but **every inference drawn from it was wrong.** The corpus in hand
was 65 MB of undecoded PDF, and the deaths that followed were an OOM caused by batching whole
documents — not by embedder throughput. With extraction repaired and `--batch-size 1`, the same
box rebuilds the same corpus at 8.7 points/min without stress. See the correction above: the
constraint this section describes does not exist.

~~That is a real constraint, not an annoyance. It means:~~

> **Struck 2026-08-23.** All three bullets rested on the rebuild not finishing. It finishes.
> They are kept, struck, so the reasoning that was actually used stays visible.

- ~~**there is no working recovery path.** "Re-index everything" is the standard answer to
  a corrupted or drifted index, and here it does not terminate;~~ — it terminates in ~1.7 h.
- ~~**the delta design assumes a rebuild exists.** `CORPUS_DELTA_CONTRACT.md` escalates to
  `mode: full` whenever a delta would be incomplete — an escape hatch that currently
  goes nowhere;~~ — `mode: full` works.
- ~~**incremental sync becomes load-bearing rather than an optimisation**~~ — incremental
  sync is an optimisation again, with a working full rebuild behind it.

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

**Gained:** ~2.7 GB of RAM returned by evicting the resident local embedder — the strongest
remaining benefit; a full re-index in minutes of API calls rather than ~1.7 hours.

*(Struck: "a rebuild path that terminates" and "`mode: full` stops being a dead end". Both
were true only while extraction was broken. The rebuild terminates today.)*

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
