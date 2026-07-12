---
description: Audit a paper/article (URL or pasted) against the literature review, the novelty claims, the specs and the RAG corpus — coverage map + verdict + draft issue
argument-hint: <URL, DOI, or "pasted">
disable-model-invocation: true
---

# /paper-audit

The user pasted or linked a paper, preprint, dataset release, or article — riparian remote
sensing, Tamarix/invasives, EO foundation models, biocontrol, phenology. Audit it against this
project's existing encoding so the user can decide in one glance.

Ported from NovaCraft's `/article-audit`, with one verdict class added that a science project
cannot do without.

> ## The verdict that matters most: **THREAT**
>
> This project's contribution is a **novelty claim**, stated plainly in
> `docs/literature-review.md` and `docs/STATUS.md`:
>
> > *"Nobody has produced a wall-to-wall, time-series, native-vs-invasive cover + change product
> > at reach scale."*
>
> **A single paper can falsify that.** If someone published it in 2024–25, the contribution
> evaporates and we need to know **before** renting a GPU, not after. The project already
> discovered — late, and by reading rather than by any gate — that CO-RIP had solved basin-wide
> extent, and that tamarisk detection was long-established. Both landed as "we are not the first."
> A third one arriving unnoticed is the most expensive mistake available.
>
> So: **actively try to falsify our novelty claim with this paper.** Do not look for reasons it is
> compatible. If it is close, say so loudly.

## Inputs

`$ARGUMENTS` is one of:
- A **URL / DOI** → fetch with `WebFetch` (for a DOI, resolve it first)
- The literal word **`pasted`** → the paper body is in the user's previous message
- Anything else → treat it as the body itself

## What to do

### 1. Read it, and get the year and the sensor right

Extract, and state up front:
- **Year**, venue, authors.
- **Sensor + resolution** (Sentinel-2 10 m? Landsat 30 m? NAIP? UAV? hyperspectral?)
- **Study area** — is it the Colorado Basin / San Juan / arid Southwest, or somewhere with no
  bearing on a semi-arid phreatophyte system?
- **Label source and its VINTAGE** — this project has been bitten by exactly this (NMRipMap is
  NAIP-2020-derived; we fit it against 2024 imagery and injected our own label noise).

### 2. Extract 5–10 load-bearing claims

Bullet form. Skip abstract throat-clearing. Prefer claims with numbers (accuracy, κ, F1, OA,
sample counts, dates).

**Comment threads and supplementary material count.** For a preprint, blog or dataset release, the
load-bearing caveat is often in the supplement, the data dictionary, or a reply thread — not the
abstract. If you could not see them, **say so** rather than fabricating.

### 3. Map each claim against our surfaces, in this order — quote the match

1. **`docs/literature-review.md`** — is this paper *already cited*? If yes, is our summary of it
   still accurate? (Cite the § number.)
2. **`docs/STATUS.md` → "Positioning"** and the literature review's "Open (the real gaps)" — does
   this claim **narrow, strengthen, or FALSIFY** a gap we assert?
3. **`docs/specs/`** — Stage 1 (delineation), Stage 2 (invasives/Tamarix), Stage 3 (annual change).
   Does it change a method we have specified?
4. **`CLAUDE.md`** + `docs/data-sources.md` — does it introduce a data source or a rule we should
   encode (`Grep` the key nouns)?
5. **`docs/RETRACTIONS.md`** and **`.claude/tombstones.txt`** — does it **retract** something we
   assert, or **retire** a value we use? If so, that is a registry entry, not a note.
6. **`docintel/corpus/seed_sources.yaml`** — is it already in the RAG corpus? Query the RAG to see
   whether we can already answer from it:
   ```bash
   cd ~/Dev/riparian-rag-harness && . .venv/bin/activate
   python -c "import docintel_server as ds; print(ds._Engine().answer('<the paper's core claim>'))"
   ```
   If the corpus answers it well, the paper is likely already covered. If not, it is a candidate
   for ingestion.

### 4. Verdict — pick exactly one

| Verdict | Meaning | Action |
|---|---|---|
| 🔴 **THREAT** | It does, or nearly does, what we claim nobody has done | **Stop and say so.** Draft an issue; propose how the positioning must change. Do not soften it. |
| 🟠 **RETRACTS** | It falsifies a claim we currently publish | Add to `docs/RETRACTIONS.md` / `.claude/tombstones.txt`; the gate will then force every doc to fall in line |
| 🟡 **GAP** | A real method/source we should adopt | Draft a GitHub issue body (below) |
| 🔵 **CORPUS** | Sound, relevant, not encoded — but belongs in the RAG, not the rules | Add to `seed_sources.yaml` (set `fetch: manual` if the publisher blocks bots — MDPI, ResearchGate and www.usgs.gov all 403 a browser UA) |
| ⚪ **COVERED** | Already cited/encoded, and our summary is accurate | Say where, and stop |
| ⚫ **OUT OF SCOPE** | Different biome, sensor, or problem with no bearing | One line, and why |

**Be willing to return THREAT.** A paper that scoops us is bad news, not a bad audit — and
finding it here is the cheapest place it will ever be found.

### 5. If GAP / THREAT / RETRACTS — draft the issue body

Include: the citation; the specific claim; which surface it hits; what changes; and — for a
THREAT — **what remains ours** after conceding the point. (CO-RIP took extent; the time axis and
the species split survived. Do that analysis honestly rather than reflexively defending.)

### 6. WRITE THE AUDIT DOWN — this step is not optional

Persist it as **`docs/audits/YYYY-MM-DD-<first-author>-<year>.md`**, and add a row to
**`docs/audits/README.md`** (the falsification log).

**Do not skip this because the conclusion has already been propagated into the docs.** That is
exactly what happened with the CSU/NREL audit: the *conclusions* reached six files within the hour,
while the *evidence and reasoning* existed only in a pull-request body — not citable, not
reproducible, and invisible to a reader of the repo.

The record must contain the **verbatim quotes** that did the work. A paraphrase of a falsifying quote
is not evidence; the next person cannot check it, and neither can a reviewer.

This directory **is** the related-work section of any publication from this project — written to
*attack* the contribution rather than to justify it. `docs/audits/README.md` explains why that is
worth publishing.

## Output shape

1. **Paper** — citation, year, sensor/resolution, study area, label source + vintage
2. **Claims** — 5–10 bullets
3. **Coverage map** — a table: claim → surface → quoted rule → covered / gap / threat
4. **Verdict** — one of the six, with the reason
5. **The audit record** — written to `docs/audits/`, logged in `docs/audits/README.md`
6. **Draft issue body** — only if GAP / THREAT / RETRACTS

See CLAUDE.md.
