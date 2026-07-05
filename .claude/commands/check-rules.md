---
description: Audit "See CLAUDE.md" cross-references for drift against the canonical rules
disable-model-invocation: true
---

# /check-rules

CLAUDE.md is the canonical source of project rules. Paraphrases of those rules live in
docs, READMEs, inline comments, skills, and `.coderabbit.yaml`. Convention: any paraphrase
ends with `See CLAUDE.md` so it's findable. This command audits every paraphrase against
the canonical rule and flags drift.

## What to do

1. **List the paraphrases.** Grep the repo for `See CLAUDE.md` (case-sensitive), excluding
   CLAUDE.md/claude.md itself:
   ```bash
   grep -rln "See CLAUDE.md" \
     --include='*.py' --include='*.cs' --include='*.ts' --include='*.tsx' \
     --include='*.sql' --include='*.md' --include='*.yaml' --include='*.yml' . \
     | grep -iv '/claude\.md$'
   ```

2. **For each match**, extract the surrounding sentence/paragraph and the nearest CLAUDE.md
   rule it paraphrases. Match by topic (e.g. a comment mentioning "geography cast for
   distance" → CLAUDE.md "Spatial Data"; "project-in-SQL / ST_AsGeoJSON" → "Data Access
   (Dapper)"; "peak growing season June–August" → "NDVI & Phenology").

3. **Compare.** For each pair, decide:
   - **Aligned** — paraphrase agrees with the canonical rule. Report and move on.
   - **Drift** — paraphrase says something subtly different (older wording, stricter/looser
     bound, missing nuance). Report the exact line + canonical wording, propose an edit.
   - **Orphan** — no matching rule exists in CLAUDE.md anymore. Report and ask whether to
     delete the paraphrase or restore the rule.

4. **Print a table** of findings: `file:line  status  topic  suggested action`. Don't
   auto-apply — output diffs and wait for confirmation per finding.

## Guardrails

- **Treat CLAUDE.md as canonical.** Never propose changing CLAUDE.md to match a paraphrase.
  If the paraphrase is "better", that's a separate conversation (a CLAUDE.md edit, which
  re-triggers the cross-reference hook).
- **One topic at a time.** Each finding gets its own confirmation.
- **Skip the PostToolUse hook output.** The `check-claude-md-refs.sh` hook just lists
  candidate files when CLAUDE.md is edited; this command is the deeper audit — it reads
  both sides of the rule.

## Why this command exists

The "See CLAUDE.md" convention is enforced lightly by the PostToolUse hook (it lists files
but doesn't read either side). Drift accumulates silently otherwise: a comment from months
ago paraphrases a rule that's since been tightened, and now contradicts the canon. Catch it
on purpose, on a cadence.
