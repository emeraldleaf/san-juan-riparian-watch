# Riparian POC — Domain & Method Vocabulary

A focused glossary so language stays consistent between humans, agentic coding
tools (Claude Code, Copilot), and review surfaces (CodeRabbit, the
architecture-reviewer agent). **Not** a rules file — for rules see `CLAUDE.md`.

Two halves: the **riparian science vocabulary** (what the project is about) and
the **encoding-loop method vocabulary** (how the project keeps agent-assisted
code from drifting — ported from the NextAurora method).

---

## Riparian science vocabulary

### Riparian zone
The band of vegetation adjacent to a stream that depends on the stream's water
table (phreatophytes: cottonwood, willow — and invasive tamarisk / Russian
olive). Its extent is controlled by **geomorphology + water-table access +
actual vegetation**, NOT by a fixed distance from a stream centerline.

*Avoid:* using "riparian buffer" to mean "a fixed-width buffer of an NHD
flowline." That is a *hydrology buffer* (an assumption), not a riparian zone (a
measured feature). See **Delineation**.

### Delineation (Stage 1)
The act of identifying **where** riparian vegetation actually is, independent of
hydrology buffers. Multi-evidence: land-cover masking (LANDFIRE EVT riparian ∧
NLCD woody-wetland ∧ NWI), terrain (HAND / valley bottom), and
groundwater-subsidy phenology (dry-season greenness persistence). The
foundation the rest of the pipeline hangs off.

*Avoid:* "buffer generation" as a synonym — that is the old fixed-width approach
being replaced.

### Weak labels
Riparian/not-riparian training labels derived from the *agreement* of existing
maps we already ingest (LANDFIRE EVT riparian classes, NLCD woody/emergent
wetlands, NWI wetlands). Not ground truth; a supervision signal. Validated
against a held-out map + NAIP high-res visual check.

### HAND (Height Above Nearest Drainage)
Terrain metric: elevation of each cell relative to its nearest drainage,
computed from the 3DEP DEM. Low HAND = hydrologically connected floodplain =
the physical envelope where riparian *can* exist. Replaces the fixed buffer as
the geomorphic container.

### Condition (Stage 2)
Whether delineated riparian is **healthy**. Multi-indicator, not NDVI-only:
NDVI-density (on pure riparian pixels), NDMI/NDWI (canopy water), NDRE/kNDVI
(chlorophyll without NDVI saturation), LiDAR canopy structure, land-surface
phenology, and **LUI** (land-use pressure).

### LUI (Land Use Intensification index)
`LUI = 5·%artificial + 3·%agricultural + 1·%pasture`, computed at reach (100 m)
and segment (500 m) scales from NLCD classes. Per Pace et al. 2022 it was the
*strongest* single predictor of riparian quality — so it is the primary
"pressure" signal feeding the unhealthy map.

### NDVI-density
Mean NDVI over **pure riparian pixels only** × the fraction of riparian pixels
in a reach cell. A density/quality proxy — must be computed on the delineated
extent, not on raw buffered pixels (mixed-pixel noise from crops/urban).

### Change / degradation (Stage 3)
The spatio-temporal signal that makes the **unhealthy riparian** map: per-pixel
multi-year trend (Theil-Sen + Mann-Kendall) on NDMI/NDVI, plus breakpoint
detection for abrupt disturbance. Unhealthy = delineated riparian ∩ (low
condition ∨ negative trend ∨ high LUI).

### Baseline vs. foundation model
Two delineation/condition methods run side by side: the **baseline**
(interpretable, paper-grounded land-cover masking + indices) and the
**foundation model** (OlmoEarth multimodal embeddings). Compared head-to-head.
The published head-to-head is **retracted** — see `docs/olmoearth-vs-rf-baseline.md`.

### Label vintage
**The year the reference labels describe, which is not the year you fetched them.**
NMRipMap v2.0 Plus (2023) was photo-interpreted from **NAIP 2020**, so it describes the
corridor as it was in **2020**. Rule: **fit and validate on imagery from the label's year;
predict any year.** Fitting 2020 labels against 2024 reflectance is label noise you inflict
on yourself — and it is worst for **invasive cover**, which is exactly what the beetle has
been changing since 2004. See CLAUDE.md.

### Calibration vs. contribution (the time axis)
**Calibration** = matching an authoritative reference for **one epoch** (CO-RIP, NMRipMap).
Necessary, but not novel — CO-RIP already did it basin-wide at κ 0.80.
**Contribution** = the **time axis**: every existing product is one frozen epoch, so an
*annual* series of riparian **extent** and of **native-vs-invasive cover** is what nobody has.
The beetle makes this necessary rather than optional: there is no un-confounded *place* left in
the basin, but Landsat reaches **1984** and *Diorhabda* arrived **2004–07**, so there is a
~20-year un-confounded *time*. See CLAUDE.md.

### Medallion (bronze / silver / gold)
One-directional data flow: bronze (raw ingest) → silver (spatial processing,
delineation, condition) → gold (aggregated analytics + composite scores). Never
write back upstream. See CLAUDE.md.

---

## Encoding-loop method vocabulary (ported from NextAurora)

### Encoding loop
The method that keeps agent-assisted code from drifting: each finding, plan,
fix, or audit becomes a rule encoded at the smallest sufficient surface and
promoted down the enforcement spectrum as it earns its keep.

### 5 surfaces
Where encoded rules live: (1) **Canon** — `CLAUDE.md` + `.claude/`;
(2) **PR rules** — `.coderabbit.yaml` path instructions; (3) **Architecture
review** — the `architecture-reviewer` agent's checklist; (4) **Procedures** —
`.claude/commands/` + `.claude/skills/`; (5) **Deep context** — `docs/` +
paired diagrams.

### 3 tiers
The enforcement spectrum: Tier 1 Convention (humans + AI on review) → Tier 2
PR-review automation (CodeRabbit, architecture-reviewer, PostToolUse hooks) →
Tier 3 Mechanical gates (build, analyzers/SonarQube, CI). *Promote down* as a
rule earns it.

### Smallest durable surface
The minimum surface that holds a rule effectively — picked on encode. A rule
that only matters in `python-etl/*.py` belongs in a path-scoped
`.coderabbit.yaml` instruction, not always-loaded CLAUDE.md.

### Lean canon
`CLAUDE.md` size budget (soft 400 / hard 500 lines). Detail beyond a
one-paragraph headline moves to a paired doc in `docs/`; the paraphrase ends
with `See CLAUDE.md` so the cross-reference audit can find it.

### Greppable paraphrases
Any paraphrase of a CLAUDE.md rule (in comments, skills, CodeRabbit config,
docs) ends with `See CLAUDE.md`. The `check-claude-md-refs.sh` hook lists them
when CLAUDE.md changes; `/check-rules` audits alignment.

### File-move discipline
`git mv` / `git rm` on a tracked file triggers `check-file-moves.sh`, which
lists stale references to the old path to fix in the same PR.
