# Execution plan — the OlmoEarth fine-tune (issue #9)

**Status:** Ready to execute · **Depends on:** the
[fine-tune ADR](../decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md) and the
[beetle-pool ADR](../decisions/2026-07-12-beetle-training-pool-ecoregion-matched.md) · See CLAUDE.md.

The *what* and the *why* are already decided. This is the *how*, costed, with the abort criteria
written **before** the money is spent.

## The headline: compute is not the constraint

| | |
|---|---|
| Control AOI (Animas + Malpais) | **428 km²** → 4.28 M px @ 10 m → **~4,180 windows** (32×32) |
| Sentinel-2 cube | 12 monthly mosaics × 12 bands × uint16 ≈ **1.2 GB** |
| Model | **`OLMOEARTH_V1_BASE`** — 207.5 M params (weights+grads+Adam ≈ **3.3 GB** fp32). *v1.1 does not resolve in the pinned stack — see the resolution below; deferred to Phase 3.* |
| Tokens/window | **9,216 on v1** (measured). v1.1's 3,072 is unavailable here. |
| VRAM | 16 GB is tight on v1 — **use batch 4 + AMP** (v1's 3× token count vs v1.1's may not fit 24 GB at batch 8). |
| Training | batch 4 + AMP, ~60 epochs → **~2–7 GPU-hours** (v1's 3× attention cost widens this) |
| **Cost of the control run** | **≈ $3–15** (RunPod L4 ≈ $0.43/hr, A10G ≈ $0.34/hr) — up from the v1.1 estimate at ~3× tokens |
| **Realistic total** incl. debugging, invasives, inference | **$40–90** |

**Spending $40 is not the risk. Spending three days debugging `rslearn` on a rented GPU is.** The plan
is built around that.

## Prior methods check — riparian analogs, not just mangrove

This is **not** a greenfield remote-sensing idea, and the scaffold's mangrove lineage hides how much
riparian-specific precedent exists. Prior Colorado River Basin work has already mapped riparian
corridor extent, riparian vegetation, tamarisk, and Russian olive using field labels,
valley-bottom / corridor constraints, Landsat/Sentinel imagery, and ML workflows. Full audit:
[`audits/2026-07-14-riparian-methods-prior-art.md`](../audits/2026-07-14-riparian-methods-prior-art.md).

1. **CO-RIP** defines riparian corridors via **valley bottoms**, then maps vegetation presence/absence
   inside them — published support for **constraining negatives to the corridor / VBET rather than
   training on arbitrary desert negatives**, and for **per-ecoregion reporting** (its accuracy varies
   by ecoregion).
2. **CSU/Walton, *Mapping Native & Non-Native Riparian Vegetation in the Colorado River Watershed***
   — the closest procedural analogue for tamarisk + Russian olive: field data, scene-based Landsat/
   Sentinel models, 2006/2016 mapping. It documents that **strong evaluation statistics still hid
   qualitatively wrong maps** — published support for our **overlay-and-look gate**.
3. **CSU 2017 occurrence/absence dataset** — published *for* species distribution modeling + RS
   detection: citable provenance for the Phase-2 field labels.

**What appears un-done is the FM experiment itself** — staged weak→strong supervision for riparian
extent and invasive-species transfer. Prior work supports the RS task and the label design; the
foundation-model fine-tune is the experimental contribution. So the framing is: **not "remote sensing
of riparian vegetation" (done, here, repeatedly), but "can an EO foundation model turn abundant weak
riparian labels into better scarce-label performance for corridor extent and invasives."**

> **Being right is not being first.** Corridor negatives, year-matched labels, and overlay-and-look
> are *validated by* this literature, not invented by us. Cite them as support; do not present them
> as novelty. And the invasives half is not cleared until the Walton report gets a direct
> `/paper-audit` (secondary synthesis is how the Evangelista claim survived, wrong, for weeks).

## The stack (verified, not assumed)

```
olmoearth-runner==0.1.14     # PyPI. Python >=3.11,<3.12 — we are on 3.11 ✓
  └── rslearn==0.0.27        # pinned by the runner; do NOT install rslearn latest (0.1.12)
```

The import name is `olmoearth_run`; the **PyPI package is `olmoearth-runner`**. There is no
`olmoearth_run` package and no `allenai/olmoearth_run` repo.

> 🔴 **This paragraph used to claim "our scaffold's class paths are correct". They were not.**
> Installing 0.1.14 (2026-07-13) showed **five of them did not exist**. Every class *name* was right
> and every *module path* was wrong — the real one is
> `olmoearth_run.runner.tools.partitioners.grid_partitioner.GridPartitioner`, not
> `olmoearth_run.partitioners.grid.GridPartitioner`. They had been written from a plausible memory
> of the package layout and **never once imported**, and the word "correct" in a spec is not
> evidence. The 18 `rslearn`/`lightning`/`torchmetrics` paths *were* right; only the five
> `olmoearth_run` ones were invented, which is exactly why it read as fine.
>
> These fail at runner startup — i.e. **Phase 1, on a rented GPU**. A $0 typo would have been found
> on a paid clock. `.claude/scripts/check-scaffold-classpaths.sh` now **imports every `class_path`
> in the scaffold** and runs in `./dev.sh --check-encoding`, so the check is mechanical rather than
> a step someone must remember. A step a human must remember to run is not a gate.

The install line is not obvious, and guessing it on a GPU clock would have cost real money. Ai2's own
[`olmoearth_projects/pyproject.toml`](https://github.com/allenai/olmoearth_projects) is the source of
truth.

---

## ✅ RESOLVED (#44, 2026-07-17): Phase 1 uses `V1_BASE`; v1.1 deferred to Phase 3

The earlier recommendation here was "use v1.1-Base." **It does not resolve in the pinned stack, and
after investigating the alternatives the decision is to use `V1_BASE` for the Phase-1 control.**

| Checkpoint | Tokens/window | Available in the pinned stack? |
|---|---|---|
| **`OLMOEARTH_V1_BASE`** | **9,216** | ✅ yes — `olmoearth_pretrain 0.0.2`, public HF weights |
| `OLMOEARTH_V1_1_BASE` | 3,072 (merges S2 bands into single tokens) | ❌ no — needs `olmoearth_pretrain ≥ 0.1.1`, and its HF weights are **gated (401)** |

**Why V1_BASE, not the effort to get v1.1:**
- v1.1 exists only in `olmoearth_pretrain 0.1.1+`, but `olmoearth-runner 0.1.14` **hard-pins
  `olmoearth-pretrain==0.0.2`**. Upgrading breaks the runner pin (the 0.1.1 API *looks* compatible —
  `Config`, `Modality`, `flexihelios`, identical `load_model_from_id` — but that is unverified against
  the 23 scaffold class paths), **and** the v1.1 weights are HF-gated (needs Ai2 approval + a token).
- v1.1's only advantage is **cost** (3× fewer tokens). Our own fair test found **v1.1 ≈ v1 in
  quality** (within noise). On a **$3–15** control run, saving 3× compute is not worth three
  compounding risks (pin break, unverified API, gated access).
- **v1.1's payoff is at SCALE — Phase 3** (basin-wide inference across the full archive), where 3×
  compute is real money *and* we will already know the approach is worth scaling. Revisit it then;
  by then, upgrading the whole runner stack can be tested properly. Tracked in #44.

`model.yaml` now names `OLMOEARTH_V1_BASE` (was the non-resolving `V1_1_BASE`), verified to resolve.
The cost table above is updated to v1's ~3× token count.

## 🎯 Two-stage supervision — use the out-of-AOI data. It is ~1000× our in-AOI supervision.

This is the single biggest lever in the plan, and the reason to be greedy about other people's data.

**The problem.** Supervision available *inside* the San Juan for the species task:

| In-AOI | |
|---|---|
| CSU field points | **167** |
| …of which beetle-defoliated | **0** |
| NMRipMap `IC` | 332 polygons — and it **conflates** tamarisk with Russian olive |

**The data we were about to ignore**, all Colorado Plateau, all CC BY-SA / CC0:

| Out-of-AOI (same ecoregion) | |
|---|---|
| **CSU tamarisk *probability* raster** — Dolores | **36,114 px** @30 m |
| **CSU tamarisk probability raster** — Green | **121,070 px** @30 m |
| CSU field points, Plateau pool | 1,096 records (**305 beetle-affected**) |
| CO-RIP riparian extent | basin-wide (incl. our AOI), millions of px — weak, 2–35 % OOB |

**The design: pre-train on abundant-and-weak, fine-tune on scarce-and-strong.**

| Stage | Labels | Imagery | Why |
|---|---|---|---|
| **A — auxiliary** | CO-RIP extent (2016) · CSU tamarisk probability, Dolores + Green (2016) | **S2 2016** | Learn the representation from ~1000× more supervision |
| **B — fine-tune** | NMRipMap (extent) · CSU field points (species, incl. defoliation) | **S2 2020** / **S2 2017** | Adapt to the real task on the labels we trust |
| **Validate** | held-out AOI windows | matching year | Report honestly, per ecoregion |

**This is also the FM's central claim, finally put to the test.** "Better accuracy from the same
scarce labels" is what a foundation model is *for*, and our literature review recorded it as
**untested** in this domain. Stage A→B is exactly that experiment: if the FM cannot convert abundant
weak supervision into in-AOI accuracy, that is a real finding about foundation models, not a shrug.

### The four guardrails — without these it is just noise

1. **Ecoregion-match the auxiliary data.** Colorado Plateau only. The beetle-pool ADR established that
   pooling across ecoregions imports domain shift; CO-RIP's own κ spans **0.42–0.90 across ecoregions**.
   Do not pour the Sonoran Desert into the loss because it is free.
2. **Confidence-weight the loss.** CO-RIP's OOB error is 2–35 % *by ecoregion* and it **over-predicts at
   high elevation** — `corip.py::ECOREGION_CONFIDENCE` already carries this (0.55 Southern Rockies,
   0.95 arid lowland). An unweighted weak label teaches the model that **upland is riparian**, which is
   the exact failure the NMRipMap crosswalk exists to prevent.
3. **Match each label source to its own year.** CO-RIP & the CSU raster are **2016** → S2 2016. NMRipMap
   is **2020** → S2 2020. CSU points are **2017** → S2 2017. Never mix a label with another year's
   reflectance; we have already made that mistake once.
4. **Mind the 30 m → 10 m boundary noise.** CO-RIP and the CSU raster are Landsat-derived; rasterised
   onto a 10 m grid, every class boundary is up to three pixels of nonsense. **Down-weight boundary
   pixels**, or run Stage A at 30 m and Stage B at 10 m.

### And the honest caveat

The CSU tamarisk raster is **Landsat-derived — and CSU themselves say Landsat cannot resolve the
tamarisk phenological signature** (*"without a different sensor with greater spectral or grain
resolution this is a difficult constraint to overcome"*). So Stage A teaches the model a **noisy,
sensor-limited** notion of tamarisk. That is fine for a *prior* and dangerous as a *target*: if Stage B
cannot pull away from it, we have merely learned to imitate the incumbent's limits. **Report the Stage-A
-only baseline alongside Stage A→B**, so the difference is visible rather than assumed.

## Phase 0 — local, free, and the entire risk

**Everything that can go wrong lives here.** Nothing is rented until Phase 0's exit gate passes.

1. **Install the stack** in a Python 3.11 venv (`olmoearth-runner==0.1.14`). ✅ **DONE 2026-07-13**
   (`.venv-olmoearth/`, gitignored). Verify with `./dev.sh --check-encoding`, which now **imports
   every `class_path` in the scaffold** — do not hand-check one symbol and call it confirmed. That
   is how the five bogus paths survived: the real import is
   `olmoearth_run.runner.tools.partitioners.grid_partitioner.GridPartitioner`. All 23 now resolve.
2. **Build the label vector layer** — the real work.
   - *Control (extent):* NMRipMap → `1 = riparian, 2 = water, 3 = agriculture, 4 = other`,
     `zero_is_invalid: true`. **Four classes, not three** — this line said `3 = other` until the
     layer was built; the scaffold's `model.yaml` has said `num_classes: 4` all along, and the
     crosswalk splits agriculture from upland. Agriculture earns its own class because it is the
     one negative that is *as green as riparian*: fold it into "other" and NDVI can no longer
     separate the classes, which is exactly the failure the validator below is built to catch.
     Woody-riparian classes only (`riparian/labels/nmripmap.py` — **never a raw fetch**).
     Water from NHD/WorldCover. "Other" balanced by sampling, **clipped to the VBET valley bottom**
     (`riparian/delineation/vbet.py`) so the negatives are corridor negatives, not desert.
   - *Invasives:* CSU points → `tamarisk / russian_olive / native / other`, with **defoliation as a
     state** (`riparian/labels/csu_points.py`, `colorado_plateau()` pool).
   - Output: GeoJSON per window, in the CRS/shape `dataset.json`'s `label` layer expects.
   - Built by `riparian/labels/label_layer.py`. Two things there are load-bearing, both about the
     negatives: they are **clipped to the valley bottom** (a desert negative teaches "is it green",
     which is not the task) and **capped at 3× positive area** (unbalanced, a segmentation head
     reaches ~90% accuracy by predicting "other" everywhere while the loss curve looks *healthy*).
2b. **Validate the labels against the imagery — BEFORE renting anything**
   (`riparian/labels/validate_layer.py`). A label layer can be schema-perfect and still be wrong in
   the only way that matters: not lining up with the pixels. Nothing in `rslearn` will say so —
   training runs, loss falls, metrics look plausible, and you find out after you have paid.
   - **Separability.** Sample peak-season NDVI from **S2 2020** (the label's own vintage) and ask
     how well NDVI alone separates riparian from corridor negatives. `AUC < 0.65` → the labels are
     broken or misaligned, **stop**. `> 0.95` is *suspicious, not good*: if one hand-computed index
     nearly solves the task, the negatives are probably desert and the task is leaking.
   - **The shift test — the one separability cannot do.** Re-score with the labels translated ±3 px.
     **If a shifted version scores better, the labels correlate with the imagery but do not sit ON
     it.** Separability still passes; every trained metric is then quietly wrong. We have been
     burned by this one's cousin — the AUC-0.23 incident *looked* exactly like a misregistration
     and was an unshuffled CV split. A real one would look identical. Measure the offset; don't guess.
     (Tie-break toward zero shift: a straight reach is invariant along its own axis, so an arbitrary
     argmax invents a displacement and reports a bug in labels that are fine.)
   - **Eyes.** Overlay the polygons on **NAIP 2020** and look. NAIP 2020 is not a proxy for the
     truth — it *is* the imagery NMRipMap was photo-interpreted from. A metric tells you the labels
     are self-consistent; only your eyes tell you they are on the trees.
3. **Materialise the Sentinel-2 cube locally** (`rslearn dataset prepare|ingest|materialize`). This is
   **CPU + network**. Do it here, not on a GPU clock — a GPU idling during a Planetary Computer
   download is money set on fire. Built by `riparian/delineation/rslearn_dataset.py`.

   > 🔴 **"~1.2 GB" was wrong, and it filled the boot disk (2026-07-13).**
   > That figure describes the **materialised** output — 238 windows of 32×32 px is genuinely tiny.
   > But **`ingest` does not download 32×32 chips.** It pulls **whole Sentinel-2 granules** into a
   > tile store: each band is a full ~110 km scene, and with `max_matches: 12` over 12 monthly
   > periods × 12 bands that is **tens of GB**. Two separate numbers were collapsed into one.
   >
   > Worse, it landed on the **wrong disk**. The dataset lives on the external drive, but `rslearn`
   > stages downloads through **`TMPDIR`**, which defaults to `/var/folders` on the *boot* volume.
   > It filled `/` to zero — hard enough that no tooling could write, including the tooling needed
   > to clean up.
   >
   > **Redirect ALL temp onto the external drive before ingest AND materialize**, e.g. `.tmp/` in
   > the repo root (gitignored). Two separate temp mechanisms escape to the boot disk, and fixing
   > only the first is a trap:
   > - `export TMPDIR=… TMP=… TEMP=…` — Python/rslearn staging (the **ingest** leak).
   > - `export CPL_TMPDIR=…` — **GDAL's own** scratch (the **materialize** leak). Setting `TMPDIR`
   >   does *not* cover this; materialize still wrote ~2.8 GB to `/` until `CPL_TMPDIR` was set.
   >   Also cap `GDAL_CACHEMAX` (e.g. 256).
   >
   > Budget **~15 GB** for the tile store (ours came to **11 GB**), not 1.2 GB. The materialised
   > windows really are ~1.2 GB — that number was never wrong, just answering a different question
   > than the one that fills your disk. Tile store + materialized output live on the data drive; the
   > *only* thing that ever touched `/` was unredirected temp.

   > ⚠️ **`materialize` exits 0 when it has done nothing.** Our first run threw
   > `NotImplementedError` on all 238 windows, swallowed it into the worker pool, and reported
   > success having written **zero** GeoTIFFs. Cause: the scaffold said `"ingest": false` — the
   > *direct-materialize* path, which requires the data source to implement `get_item_by_name`.
   > Planetary Computer's `Sentinel2` inherits the base version, which **raises
   > `NotImplementedError` by design**. It is now `"ingest": true`.
   > **Never trust the exit code**: call `rslearn_dataset.verify_materialized()`, which asserts the
   > rasters are on disk. A green exit that means "nothing happened" is the most expensive kind of
   > green — on a GPU you would train on an empty cube and the loss would fall anyway.
4. **Dry-run on `OLMOEARTH_V1_NANO`, MPS/CPU, 1 epoch, a handful of windows.** ✅ **DONE 2026-07-14.**
   Reproduce with `olmoearth_run_data/riparian_extent/make_dryrun_config.py` (derives the dry-run
   from the canonical `model.yaml`, so it exercises the real wiring, not a lookalike). The run shook
   out **four more config bugs the GPU would have hit on step one**, each fixed:
   - **`OLMOEARTH_V1_1_BASE` does not resolve** — only `V1_{NANO,TINY,BASE,LARGE}` exist in this
     rslearn. The canonical config's own comment predicted the fallback; Phase 1 must use `V1_BASE`.
   - **Decoder `in_channels` was `768` (BASE) but NANO emits `128`.** The pooling head silently
     needs the encoder's embedding width; wrong on any non-BASE model.
   - **The pooling decoder misreads a temporal cube.** `SegmentationPoolingDecoder` broadcasts to
     `image.shape[1:3]`, which on our 4-D `[bands, timesteps, H, W]` input grabs `(timesteps, H)`,
     not `(H, W)` — so it emitted a `12×2` prediction against a `2×2` target. Fixed by
     `riparian.delineation.decoders.TemporalSegmentationPoolingDecoder`, which reads the true last
     two axes. **The whole approach depends on 12 monthly mosaics, so a decoder that cannot consume
     a temporal stack is not a small bug.**
   - **`num_classes` was `4`, but the crosswalk emits four *real* classes.** With
     `zero_is_invalid: true`, class 0 is the ignore label, so four real classes need `num_classes: 5`.
     The scaffold was authored for the old three-class scheme. Crashed with `Target 4 is out of
     bounds`; now pinned by `tests/test_class_scheme_contract.py` so the crosswalk and the config
     cannot drift apart again.

> ### ✅ Phase-0 exit gate — do not rent a GPU until ALL of these hold
> - `olmoearth-runner` imports, and **every** scaffold `class_path` resolves — checked mechanically
>   by `./dev.sh --check-encoding`, not by eye. ✅ 23/23 (2026-07-13; five were broken).
> - **The label layer passes `validate_layer.report()`** — NDVI separability is not BROKEN, and the
>   shift test finds no meaningful offset. ✅ AUC **0.752** (peak-season, water-excluded; 0.777→0.740→0.752),
>   with a marginal ~1 px offset to confirm by NAIP overlay — Farmington reach.
> - The dataset materialises and `rslearn model fit` **completes one epoch without error**. ✅ 238
>   windows materialised + verified on disk; NANO fit ran 3 epochs clean on CPU.
> - Loss is **finite and decreasing**. ✅ no NaN/inf; val_loss 1.455 → 1.428 → 1.401 over 3 epochs.
> - Predictions are **spatially aligned** with the labels (overlay them and look — the AUC-0.23
>   incident was a spatial-alignment scare that turned out to be an unshuffled CV split; a real
>   misalignment would look identical). ⚠️ **Deferred, on purpose:** the smoke-test decoder is the
>   pooling head, which broadcasts one prediction per window — a spatial overlay would be uniform
>   and prove nothing. Label↔imagery alignment is already established (shift test above); prediction
>   overlay becomes meaningful once Phase 1 runs a per-pixel decoder. **See "open modelling call".**
>
> **✅ RESOLVED + WIRED (#45, 2026-07-17): per-pixel `UNetDecoder`.** The scaffold mirrored mangrove
> with `SegmentationPoolingDecoder` — one label per window, broadcast to all pixels. Our windows are
> *not* single-class (a 32×32 window holds riparian *and* upland), extent is inherently per-pixel,
> and — decisively — the CPU pre-flight's bar is a *pixel-level* ROC that a per-window head cannot be
> scored against. `model.yaml` now uses `UNetDecoder(in_channels=[[2, 768]], out_channels=5)`
> (one feature map at 1/patch_size, V1_BASE embedding 768 → per-pixel logits). Validated by a NANO
> dry-run: 2 epochs clean, val_loss 1.490 → 1.290, and the per-class pixel metrics are now
> non-degenerate (`riparian_precision 0.35`, `riparian_recall 0.24` — real, spatially-varying, not
> the uniform broadcast). This also un-blocks the prediction-overlay alignment check.

## Phase 1 — the extent control (GPU)

Per the ADR + the resolved decisions: `OLMOEARTH_V1_BASE` (#44), **per-pixel `UNetDecoder`** (#45),
`FreezeUnfreeze` (unfreeze @ epoch 20, 10× LR), **12 monthly S2 mosaics**, spatial split.

- **AOI: Animas + Malpais only. Turkey Creek is HELD OUT** — its only reference is CO-RIP, which
  over-predicts in the Southern Rockies (confidence 0.55). A control fed weak, biased labels cannot
  do a control's one job.
- **Imagery: Sentinel-2 2020** — NMRipMap is NAIP-2020-derived. Fit on the label's year.
- **Compare against the PIXEL-level RF baseline: F1 0.90–0.92.** *Not* the 0.701 patch-level number —
  that belongs to the frozen-embedding experiment, and using it would flatter the model by ~0.2 F1.

> ### 🚦 GATE — if extent lands well below ~0.90 pixel F1: **STOP.**
> Do not proceed to invasives. A broken pipeline and a hard task produce the same bad number, and
> that ambiguity is the whole reason this control exists. Debug, then re-run.

## Phase 2 — invasives (GPU)

Same cube, same code path; swap the label layer.

- **Train on the ecoregion-matched Colorado Plateau pool** (Escalante + SouthWest_CO): 1,096 records,
  610 invasive, **305 beetle-affected** (117 defoliated / 145 mixed / 43 dead).
- **Imagery: Sentinel-2 2017** — the CSU points are a 2017 field season.
- **The San Juan is an OUT-OF-SAMPLE validation set, not a held-out split.** We are testing transfer
  across a prevalence gap (Escalante 21.6 % live tamarisk vs San Juan 74.1 %), and must say so.
- **Defoliation is a class, never an absence.** A defoliated stand is still *Tamarix*.

## Phase 3 — the contribution (mostly CPU)

Roll the calibrated model across the archive: **annual extent** and **annual native-vs-invasive
cover**. Inference is embarrassingly parallel and needs no training GPU — per the hosting ADR, this is
on-demand batch with **zero idle cost**.

Sensor choice is decided **after Phase 1, on evidence**: Sentinel-2 (10 m, 2016→) resolves the corridor
but misses the pre-beetle era; Landsat (30 m, 1984→) spans it but may be too coarse. **If the 10 m
control barely resolves the corridor, 30 m will not.**

---

## Risk register — the honest version

| Risk | Likelihood | Mitigation |
|---|---|---|
| **`rslearn` dataset build fights us** | **High** — we have never run it | It is Phase 0, it is free, and it is the exit gate. This is the plan's whole shape. |
| Label layer geometry/CRS mismatch | Medium | Overlay predictions on labels and *look*. Do not trust a metric to reveal a spatial bug. |
| 32×32 windows (320 m) too coarse for a narrow corridor | Medium | Corridors are 50–200 m; a window will contain riparian *and* upland. If recall collapses, try patch 1 / larger windows before blaming the model. |
| OOM on 16 GB | Low | Take 24 GB. The difference is ~$0.10/hr. |
| Beetle transfer fails (Escalante → San Juan) | **Medium-high, and interesting** | It is a *finding*, not a failure — pre-registered in the beetle-pool ADR. |
| Cost overrun | Low | Hard cap **$100**. At $0.43/hr that is 230 GPU-hours; the plan needs <15. |

## What we are NOT doing

- **No always-on GPU.** On-demand batch only (hosting ADR).
- **No Turkey Creek in the control.**
- **No blended AOI-wide accuracy number.** CO-RIP's κ spans 0.42–0.90 *across ecoregions*; a single
  number would hide exactly the effect we care about. **Report per region.**
- **No fitting a label source against the wrong year.** NMRipMap → 2020, CSU points → 2017, CO-RIP →
  2006/2016. `corip.label_from_pixel()` raises on an unmodelled year; this is enforced in code.

## Immediate next action

**Phase 0, step 2: build the label vector layer.** It is the critical path, it is free, and every
downstream phase is blocked on it.
