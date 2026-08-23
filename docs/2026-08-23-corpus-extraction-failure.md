# When a missing library became a 65 MB document

**2026-08-23** · post-mortem. The corpus index lost three quarters of its content, and every
explanation I offered for it was wrong until I looked at the machine.

## What happened

The RAG index that both agents answer from dropped from **988 points to 242**. No full
re-index would finish. Over one evening I proposed three causes and acted on two of them
before checking any:

1. *Something deleted the points.* I went looking for snapshots to restore from. There were
   none.
2. *The box is too slow to rebuild.* I wrote a decision record proposing to move dense
   embeddings to a paid API.
3. *The chunker is mangling tables.* True, and worth fixing, but unrelated.

The actual cause: **the box could not import a PDF library.** Every specialised extractor
failed, and the last-resort fallback did this:

```python
text = file_path.read_text(encoding='utf-8', errors='ignore')
```

On a PDF that is not a degraded read. It is the decoded remains of compressed streams,
embedded fonts and image data, with anything undecodable silently dropped.

Reproduced exactly. Running the old path over one 75 KB paper yields **21,491,883
characters**. The box's stored copy of that document was **21,490,814**. The same bytes.

| | the box | a known-good copy |
|---|---:|---:|
| documents | 21 | 76 |
| total characters | 64,997,130 | 2,147,710 |
| extraction method | `basic_text` (100%) | docling / pypdf2 / markdown |
| projected chunks | ~20,145 | ~1,421 |

So the index was being asked to embed roughly twenty thousand chunks of binary noise. Every
run died partway. **Nothing was ever deleted, and the hardware was never the limit.** It was
a write that could not finish, and the 242 points are simply where the last attempt stopped.

## Why nothing caught it

The output was *plausible at every checkpoint*. The fetch succeeded. The preprocessor
produced valid JSONL. The documents had text in them, and the text was even mostly ASCII,
because a PDF's internals contain plenty of it. Nothing threw.

An earlier fix had already noticed the neighbourhood of this problem and lowered the
**confidence score** on binary-format fallback output, with a comment saying raw bytes
"produce garbage". That fix treated the symptom. The garbage still flowed downstream, still
got chunked, still got embedded. Confidence is metadata; the bytes were the problem.

The one signal that was unmissable was **size**, and nothing was looking at size.

## What found it

A read-only probe, after a rule I had already written down and then ignored twice that same
evening: *look at the machine before changing it.*

The probe printed per-document size, extraction method, and one discriminating test —
**repetition**, the share of distinct fixed-size blocks in each document. That test is what
settled the diagnosis. A looping extractor emits the same block many times and scores near
zero. These documents scored **0.95 to 1.00**: the bulk was genuinely distinct content,
which is the signature of decoded binary rather than a loop.

Size alone would have said "something is wrong". Repetition said *what*.

## The fix

Two layers, because one of them can be overwritten.

**The extractor refuses the binary fallback.** It returns empty text, confidence 0, and an
explicit `extraction_failed` marker, and logs an error naming the file. A missing extractor
must look like a missing extractor, never like a large document.

**The ingest refuses to index byte-decoded documents** and exits non-zero naming them. This
second guard lives in our own code deliberately: the indexing library is vendored, and its
re-sync procedure is a straight file copy, so a check living only upstream could be reverted
by a routine update without anyone noticing.

The predicate prefers the metadata flag and falls back to two prose signals — characters per
word, and the share of letters and whitespace — so it still works on documents preprocessed
before the flag existed. Verified against 76 known-good documents including 12 real PDFs:
**no false positives**, and it catches the garbage by metadata and by heuristic independently.

## What this changed about the plan

**A decision record was written on a false premise.** The ADR proposing paid API embeddings
argued that the rebuild "does not finish" because the local embedding model cannot keep up on
an 8 GB box. That is not why it did not finish. Faster embeddings against 65 MB of noise
would have failed faster and cost money doing it. The ADR may still be right on its merits;
it is no longer supported by the evidence it cited, and it now says so.

**Snapshots were added anyway, and immediately justified themselves.** Every mutating path
now snapshots the collection first. The commit that added the step triggered a re-index on
its own — the workflow fires on corpus-code changes, which I had not anticipated — and that
run captured the collection before touching it. The fix validated itself on an accidental
trigger of its own making.

## What it says about the method

The encoding loop mechanizes textual honesty thoroughly: retired identifiers, withdrawn
claims, orphaned documents, canon size. On 2026-08-21 a reach-provenance failure showed it
had no tier for **spatial** honesty. This one shows the same gap one layer lower, at the
**bytes**.

Three failures now share a shape. Every surface reported success. Every check that ran was
checking something else. And in each case a single cheap read-only measurement — the reach's
actual bbox, the layer's real extent, this file's size — would have settled in seconds what
reasoning could not settle in hours.

The rule that keeps being relearned: **measure the artifact, not the pipeline that produced
it.** A pipeline reports what it believes it did. Only the artifact knows.

See also: [the corpus is a surface](corpus-automation.md) ·
[the reach-provenance gap](2026-08-21-reach-provenance-gap.md) · [method](method.md)
