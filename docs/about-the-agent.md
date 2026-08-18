# How this agent works — the Quartzose RAG platform

The question-answering agent on this site is not a chatbot bolted on at the end. It is a **grounded
retrieval-augmented-generation (RAG) system** — every answer is assembled from the project's own
documents and the supporting literature, with clickable citations, so a reader can check the source
rather than trust the model. It runs on **Quartzose**, a RAG platform built for this and adjacent
projects. This page explains how it works, because *how the agent was engineered* is itself part of
what this portfolio demonstrates.

> **Proof of concept.** Like everything on this site, the agent is a research prototype. It answers
> from a fixed corpus and can still be wrong; treat its output as a guide to the sources, not as
> ground truth.

## The pipeline, end to end

A question flows through these stages:

1. **Ingestion (offline).** The corpus — this project's own docs (methods, specs, decisions, audits,
   findings) plus the foundational literature (CO-RIP, NMRipMap, USGS beetle studies, remote-sensing
   papers) — is chunked and embedded two ways: a **dense** semantic vector (Snowflake Arctic
   embeddings) and a **sparse** lexical vector (BM25). Both are stored in **Qdrant**, a vector
   database, as a hybrid index.

2. **Hybrid retrieval.** A query is embedded the same two ways and searched against both indexes.
   Dense search catches *meaning* ("riparian corridor" ≈ "streamside vegetation"); sparse BM25 catches
   *exact terms* (a specific reach name, a metric). Their results are fused with **Reciprocal Rank
   Fusion (RRF)** into one candidate pool.

3. **Query anchoring.** The corpus deliberately mixes *this project's* work with the external field
   literature, which makes a bare method question ambiguous — "how was riparian vegetation derived?"
   matches a field-survey paper as readily as the project's satellite pipeline. Method and
   self-referential questions are therefore **anchored** to the project's framing before retrieval, so
   they surface the project's own docs; pure-science questions are left alone and still reach the
   literature.

4. **Reranking.** A **cross-encoder reranker** (Voyage `rerank-2.5-lite`, served via OpenRouter)
   re-scores the pooled candidates by reading each *(query, passage)* pair jointly — far more precise
   than the first-stage vector similarity. Only the top few passages survive.

5. **Corrective grading (CRAG).** Before generating, the surviving passages are graded for relevance.
   If retrieval came back weak, the system can widen or decompose the query rather than answer from
   thin context. This is what lets the agent say *"the sources don't cover that"* instead of
   confabulating.

6. **Generation.** A hosted large language model writes the answer **grounded in the graded passages**,
   citing them inline. The visitor can pick the model tier (a fast model, a balanced default, or Ai2's
   OLMo when a provider serves it); the answer **streams** token by token.

7. **Guards.** Three filters wrap the flow: a **QueryShield** (input), a **PassageShield** (retrieved
   context), and an **AnswerScrubber** (output) — defense in depth against prompt injection and leakage.

A **semantic cache** short-circuits repeated or near-identical questions before any model call, and a
per-IP **rate limiter** plus a hard provider spend cap keep a public demo from running up a bill.

## Why hybrid + rerank, not just embeddings

Pure dense retrieval misses exact terms; pure keyword search misses paraphrase. Hybrid + RRF gets both
into the pool, and the cross-encoder reranker then does the precise ordering a bi-encoder can't. The
reranker is the single highest-leverage relevance component — which is exactly why *how it is served*
turned into the sharpest engineering lesson on the project.

## A worked engineering lesson: the reranker that ate the box

The agent originally ran the reranker **locally** — an ONNX cross-encoder in the API process. On the
small (8 GB) deployment box it began OOM-killing the backend under load. The instinct was "the box is
too small," but the honest path was to **measure**: a `memray` profile of a single query showed
onnxruntime allocating ~2.5 GB inside one inference, and — the real bug — a **fresh model session
built per request** (the retrieval pipeline was rebuilt each call), whose memory arenas *stacked* under
concurrency to 6.7 GB and tripped the kernel.

The first fix cached the session and serialized inference — correct, but it only *contained* the
problem (idle RSS still parked at 4 GB). The better fix was to ask a different question: **does the
reranker need to run on this box at all?** Moving it to an API cross-encoder (Voyage via OpenRouter)
removed the local model entirely: **backend idle memory dropped from ~4 GB to 218 MB**, latency
improved, and — measured, not assumed — the API reranker was both *higher quality* and *cheaper per
query* than the local one it replaced. The cheapest fix was to delete the code.

That episode is the method in miniature: *profile before hypothesizing; "small model" ≠ "small memory";
the best fix can be to run it elsewhere.* The discipline that turns lessons like this into permanent
guardrails is described in **the engineering method** ([OKL & the encoding loop](about-okl.md)).

## A worked engineering lesson: the answers that wouldn't come

Under two people asking questions at once, the agent stopped answering — requests hung, then timed out.
The health check stayed green and the box was not out of memory, which ruled out the obvious. Working
without the server logs at first, the temptation was to *theorize*, and the first three theories were
all wrong: too many grading calls, then a re-retrieval cascade, then a saturated local embedder. Each
was plausible; none survived contact with the evidence.

The logs, once reachable, said it in one line: **`Generation complete (137.11s)`**. Retrieval had
finished in three seconds and the graded pipeline was fine; **generation** was the entire cost. The
answer model — a 72-billion-parameter Qwen — was producing about **8 tokens per second**, and under two
concurrent users the provider throttled it to ~6. A full answer at that rate takes over two minutes.

The root cause was not the model but *where it was served*. On OpenRouter a model is routed to one of
several backend providers, and that 72B model had only **two** — both ordinary GPUs whose speed swings
with load, fast one day and crawling the next. The fix had two parts: **backpressure** (a concurrency
limit, so a burst of requests queues gracefully instead of collapsing the box) and **a model with a
fast home** — one served on Groq's inference silicon at ~250 tokens/second, pinned via OpenRouter's
throughput routing. The same answer that took 137 seconds now streams in about four, and the speed no
longer rides on a daily provider lottery.

The lesson in miniature: *a green health check is not a working system; get the real logs before you
theorize; and for a hosted model, throughput is a property of the **provider**, not the model — so pick
a model that has a fast one.*

## Honest limits

The agent is grounded, but grounding is not infallibility: retrieval can miss, the model can
misread a passage, and the corpus is a snapshot. Citations exist precisely so a reader can verify.
Nothing here is a substitute for the primary sources it points to.

> This page paraphrases the project's architecture; the canonical conventions and the do-not-modify
> rules live in the repository's project instructions. See CLAUDE.md.
