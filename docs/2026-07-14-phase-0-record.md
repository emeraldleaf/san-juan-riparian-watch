# Phase 0 — the record

**What this is.** A single, honest account of Phase 0 of the [GPU fine-tune execution
plan](specs/2026-07-12-gpu-finetune-execution-plan.md): what we built, what broke, the methods that
generalised, the trade-offs we accepted, and the decisions that are still open. The plan is the
*intent*; this is the *record*. Where they disagree, this is what actually happened.

**Dates:** 2026-07-13 → 2026-07-14. **Status: Phase 0 exit gate MET.** Cleared to rent a GPU — but
read [the open decisions](#open-decisions--before-a-gpu) first; one of them changes what the control
measures.

**The framing that made Phase 0 worth doing.** Everything here ran on a laptop, for $0. The entire
purpose was to move every discoverable failure *off* the GPU clock — because a bug found on a rented
A100 is the same bug, billed. It paid off literally: **seven distinct traps** surfaced here
(method receipts 13–19), and every one of them would otherwise have failed on GPU step one.

---

## What we did

Four steps, each with a method that outlived the step.

### 1. Installed the stack, and checked every class path *mechanically*

`olmoearth-runner==0.1.14` into an isolated `.venv-olmoearth`. The plan listed "confirm
`GridPartitioner` imports" as a step for a human to remember — and a step a human must remember is
not a gate. So the check is now `check-scaffold-classpaths.sh`, which **imports every `class_path`
in the scaffold** and runs in `./dev.sh --check-encoding`. It immediately found **5 of 23 paths did
not exist** (the spec had asserted they were "correct"). All names right, all module paths wrong,
never once imported. 23/23 resolve now.

### 2. Built the label layer — and validated it against the imagery *first*

`riparian/labels/label_layer.py` builds the extent target from NMRipMap. Two decisions carry it,
both about the **negatives**:

- **Clipped to the VBET valley bottom.** A model asked to separate riparian from the desert learns
  "is it green", which is not the task and dies in a dry year. Corridor negatives are the hard ones.
- **Capped at 3× positive area.** Unbalanced, a segmentation head reaches ~90% accuracy predicting
  "other" everywhere while the loss curve looks *healthy*.

Then the part that answers "how do you know the labels are any good": `validate_layer.py`, three
tests cheapest-first, because **a label layer can be schema-perfect and still not line up with the
pixels, and nothing downstream will tell you** — training runs, loss falls, metrics look plausible,
and you find out after you've paid.

| test | question | result on the Farmington reach |
|---|---|---|
| **Separability** | does peak-season NDVI (S2 2020, the labels' own vintage) separate riparian from corridor negatives? | **AUC 0.752** — in the plausible band; not <0.65 (broken) nor >0.95 (leaking) |
| **Shift** | does a *translated* label mask score better — i.e. are they aligned, or merely correlated? | best offset **(1, 0)**, +0.013 — a marginal ~1 px (10 m) offset; see caveat |
| **Eyes** | overlay on NAIP 2020, the imagery NMRipMap was drawn from | (manual — **do this before Phase 1**, see caveat) |

> **Corrected twice, against ourselves — 0.777 → 0.740 → 0.752.** The first pass reported **AUC
> 0.777, shift (0,0)** from an ad-hoc harness. CodeRabbit's review caught **two** contaminations:
> 1. **Water leaked into the negatives** (class 2), trivially separable and inflating the score.
>    The negative set is *corridor* — agriculture + other (3/4), not water.
> 2. **All 12 monthly mosaics were averaged**, but only **3 are peak-season** (the cube spans
>    Jan–Nov 2020 for phenology). Dormant-month NDVI dragged riparian toward upland — the exact
>    error CLAUDE.md's peak-season rule exists to prevent. Restricting to June–August lifts riparian
>    median NDVI from a dormant-contaminated **0.320 to 0.463** (physically sensible for lush summer
>    riparian) and the AUC to **0.752**. Still healthy, now honest.
>
> Reproduce with `olmoearth_run_data/riparian_extent/validate_materialized.py`, which scores the
> **materialised cube** (the exact training pixels), peak-season and water-excluded — not the ad-hoc
> harness the 0.777 came from.
>
> The fix also swapped the per-window shift test (noise-dominated on 32×32 tiles) for a **global,
> pooled-across-windows** one, which surfaces a **marginal ~1 px (10 m) offset**: pooled AUC 0.765 at
> (1,0) vs 0.752 unshifted. **Not a code bug** — a rasterisation convention flip would crater the AUC
> to ~0.5, not nudge it by 0.013. It is the sub-pixel registration slack of fusing 0.6 m NAIP-drawn
> polygons onto a 10 m grid. **Confirm with the NAIP overlay before Phase 1**: a real 1 px label
> offset blurs a segmentation boundary, and only the eyes-on check settles whether this is that or slack.

The shift test exists because we've been burned by its cousin: the AUC-0.23 incident *looked*
exactly like a misalignment and was an unshuffled CV split. A real one looks identical — so measure
the offset, don't guess. It also caught a bug in *itself* (a straight reach is invariant along its
own axis, so ties must break toward zero shift, or it cries "registration bug" on aligned labels).

### 3. Materialised the Sentinel-2 cube — 238 windows, verified on disk

`rslearn_dataset.py` builds the dataset: 238 windows (32×32 px @ 10 m, UTM, **12 monthly mosaics
spanning 2020 Jan–Nov** — the full seasonal trajectory is the phenology signal; only ~3 fall in peak
season, which is why the validator must filter to them), skipping **777 pure-negative windows** —
each a full S2 download that teaches
nothing. Then `prepare → ingest → materialize`. Result: **2,856 GeoTIFFs, 11 GB tile store**,
confirmed by `verify_materialized()` — which checks the rasters are on disk rather than trusting the
exit code, because the exit code lied (see findings).

### 4. Dry-run: NANO fine-tune, one epoch, loss decreasing

`make_dryrun_config.py` derives a laptop config from the canonical `model.yaml` (so the smoke test
exercises the *real* wiring). `rslearn model fit` on CPU, NANO encoder, spatial 158/80 split:

- completes without error — **3 epochs clean**
- loss finite and decreasing — **no NaN/inf; val_loss 1.455 → 1.428 → 1.401**

Getting there shook out four more config bugs (below).

---

## Findings — every one free here, billable on a GPU

These are method receipts 13–19. Grouped by theme.

### The gate that guards the gates
- **13 — The merge gate demanded a CodeRabbit *check-run*.** CodeRabbit posts none for an on-demand
  review, so it blocked four already-reviewed PRs *forever*; it was also too weak (a check proves it
  *ran*, never *which commit it read*). Fixed to judge by the commit CodeRabbit's walkthrough names.

### The scaffold was written from memory, never executed
- **14 — 5 of 23 `class_path`s did not exist**, and the spec called them "correct". Names right,
  modules wrong. → mechanical import gate.
- **19 — `SegmentationPoolingDecoder` misreads a temporal cube.** It broadcasts to
  `image.shape[1:3]`; our input is 4-D `[bands, timesteps, H, W]`, so it grabbed `(timesteps, H)`
  and predicted `12×2` against a `2×2` target. **The whole approach *is* the 12-mosaic time axis**,
  so a decoder that can't consume a temporal stack is not a corner case. → a `Temporal…` adapter
  reading the true last-two axes.
- **18 — `num_classes: 4` was wrong.** The crosswalk emits four *real* classes and `zero_is_invalid`
  reserves class 0, so it needs **5**. Authored for the old 3-class scheme. Crashed `Target 4 is out
  of bounds`. → pinned by `test_class_scheme_contract.py` so crosswalk and config can't drift again.
- Also (same run, same cause): `OLMOEARTH_V1_1_BASE` doesn't resolve (only `V1_{NANO,TINY,BASE,LARGE}`);
  decoder `in_channels` was 768 (BASE) but NANO emits 128.

### Green that means "nothing happened"
- **15 — `rslearn dataset materialize` exited 0 having written zero files.** `"ingest": false`
  needs `get_item_by_name`, which Planetary Computer's `Sentinel2` **raises by design**. All 238
  windows threw; the exception was swallowed into a worker pool. → `verify_materialized()` checks
  disk, never the exit code. *On a GPU you'd train on an empty cube and the loss would fall anyway.*

### The disk (three traps wearing one costume)
- **16 — "~1.2 GB" was really ~11 GB.** That figure is the *materialised chips*; `ingest` pulls
  whole 110 km granules. And it staged through `TMPDIR` on the **boot disk**, filling `/` to zero —
  hard enough that no tool could write, *including the tools to clean up*.
- **17 — `TMPDIR` on the data drive, and materialize *still* wrote 2.8 GB to `/`.** **GDAL keeps its
  own temp, `CPL_TMPDIR`**, which `TMPDIR` doesn't cover. Fixing one leak hid the second. → redirect
  *every* temp mechanism (`TMPDIR`/`TMP`/`TEMP`/`CPL_TMPDIR`), budget the tile store not the output.

---

## Methods that generalised

Principles this phase reinforced, worth applying beyond it:

- **Validate against the ground truth, not the schema.** A well-formed label that's off the pixels
  is worse than a malformed one, because it passes silently. Separability + shift do this cheaply.
- **Never trust an exit code that can mean "did nothing".** Verify the artefact exists
  (`verify_materialized`), don't believe the return value. This repo keeps getting bitten by green.
- **A step a human must remember is not a gate.** Every check that mattered became mechanical:
  class-path import, class-count contract, the drift gates.
- **Split by space, never at random.** Hash the grid cell. A random train/val split leaks
  autocorrelated neighbours across the boundary and inflates every val metric — the AUC-0.23
  incident's twin.
- **Redirect *all* scratch, then guard it.** One temp env var is never all of them.
- **Correct claims in place, don't quietly edit them.** The spec's "class paths are correct" and
  "~1.2 GB" are struck through with what actually happened, so the error is legible, not erased.

---

## Trade-offs we accepted (and where they might bite)

- **Ran without the VBET corridor clip.** The negatives are NMRipMap's own non-riparian classes —
  already corridor-ish, but not the tight valley-bottom clip the design calls for. The clip should
  *tighten* separability, not loosen it, but **we haven't measured that**, so we don't claim it.
- **One reach, not the basin.** Farmington is well-behaved. The number to watch is whether AUC 0.752
  holds on the narrow headwater corridors, where a 320 m window is mostly upland.
- **Pooling decoder = one label per window.** The smoke test kept the scaffold's mangrove-style
  per-window classifier. Our windows are *not* single-class, so this is a real modelling limitation
  we accepted *for the dry-run only* — see below.
- **NANO for the smoke test, not the science.** NANO (128-dim, 1.4 M params) proves the pipeline;
  Phase 1 uses `V1_BASE`. The dry-run's *loss values* mean nothing on their own — only that they're
  finite and fall.

---

## Open decisions — before a GPU

1. ~~**Per-window vs per-pixel decoder**~~ → **RESOLVED 2026-07-17: per-pixel (`UNetDecoder`).**
   Three independent arguments converged, and the third is decisive:
   - our 32×32 windows are **not single-class** (they hold riparian *and* upland);
   - the prior-art audit found CO-RIP / Furuya / Walton all map **pixel/area extent**, not
     one-class-per-window ([audit](audits/2026-07-14-riparian-methods-prior-art.md));
   - **the CPU pre-flight's bar is a *pixel-level* ROC** at 100–400 px/class
     ([decision memo §6](audits/2026-07-16-DECISION-MEMO-olmoearth-gpu.md)). The scaffold's
     `SegmentationPoolingDecoder` emits one prediction per window broadcast to all pixels, so it
     **cannot be scored against that bar at all**. Per-pixel is now *required to measure the thing
     we defined*, not merely preferable.

   This also un-blocks the deferred prediction-overlay alignment check (a per-window prediction
   overlays uniformly and proves nothing). The dry-run deliberately did not make this call; the
   evidence did.

2. **Sensor: Sentinel-2 (10 m, ~2015→) vs Landsat (30 m, 1984→).** Still open — but the
   [Malpais reach resolvability note](audits/2026-07-16-malpais-reach-generalization-note.md)
   supplies the first real measurement and **sharpens it into a genuine dilemma rather than a
   preference**:
   - the corridor is ~80–100 m wide → **~8 px at 10 m, but only ~3 px at 30 m**;
   - aggregate corridor-vs-upland NDVI *contrast* is nearly resolution-invariant (0.338 → 0.333),
     so **Landsat can track corridor greenness trends**;
   - but at 30 m the corridor **blurs into adjacent irrigated fields** — and irrigated agriculture is
     *precisely* the confound for the native-vs-invasive split.

   So: **only Landsat reaches the pre-beetle era (1984)** that separates "Tamarix senesces late" from
   "defoliated Tamarix browns early" — yet 30 m cannot cleanly delineate the corridor or keep
   phreatophytes out of the cropland it must be distinguished from. These may be **two products, not
   one compromise**. Decided after the extent control lands.

3. **Phase 1 go / no-go gate — now has a second, harder bar.** The original still stands: if extent
   lands *well below* the pixel-level RF baseline (F1 0.90–0.92 — **not** the 0.701 patch-level
   number), stop and debug. But the CPU pre-flight adds the bar that actually matters:
   **fine-tuned OlmoEarth-Base must beat fine-tuned *Presto*'s ~0.75 ROC on hard-source species
   transfer — not merely beat RF**, because a free 0.82 M-param CPU model already beats RF there
   (+0.04–0.08). If it cannot, the honest report is that the GPU bought nothing a laptop didn't.

4. 🔴 **NEW — the target checkpoint does not exist.** The plan and the decision memo both name
   `OLMOEARTH_V1_1_BASE`; the pinned stack (`olmoearth-runner 0.1.14` → `rslearn 0.0.27`) has only
   `V1_{NANO,TINY,BASE,LARGE}`. Use `V1_BASE` and **re-cost at ~3×** (9,216 vs 3,072 tokens/window;
   may not fit 24 GB at batch 8), or unpin `rslearn` — a Phase-0 exercise, not a GPU-clock discovery.

---

## Reproduce

```bash
# temp MUST live on the data drive — all four, not just TMPDIR (finding 17)
export TMPDIR=.tmp TMP=.tmp TEMP=.tmp CPL_TMPDIR=.tmp GDAL_CACHEMAX=256
DS=olmoearth_run_data/riparian_extent/dataset

.venv-olmoearth/bin/python -m rslearn.main dataset prepare     --root "$DS" --workers 8
.venv-olmoearth/bin/python -m rslearn.main dataset ingest      --root "$DS" --workers 4
.venv-olmoearth/bin/python -m rslearn.main dataset materialize --root "$DS" --workers 2
# then verify_materialized() — never trust the exit code

PYTHONPATH=python-etl \
.venv-olmoearth/bin/python olmoearth_run_data/riparian_extent/make_dryrun_config.py "$DS" .tmp/dryrun.yaml --epochs 3
PYTHONPATH=python-etl \
.venv-olmoearth/bin/python -m rslearn.main model fit --config .tmp/dryrun.yaml
```

**Companion docs:** the [execution plan](specs/2026-07-12-gpu-finetune-execution-plan.md) (intent +
inline fixes), [the method](method.md) (receipts table, findings 13–19), and
[OlmoEarth vs RF](olmoearth-vs-rf-baseline.md) (why the fine-tune is being tried at all).
