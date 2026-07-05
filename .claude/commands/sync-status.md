---
description: Refresh docs/STATUS.md from recent git activity + open issues
disable-model-invocation: true
---

# /sync-status

Update [docs/STATUS.md](../../docs/STATUS.md) so it accurately reflects where the project
is *right now*. STATUS.md is the cross-session entry point (surfaced by the `inject-status.sh`
SessionStart hook) — when it goes stale, every future session starts with bad orientation.

## What to do

1. **Read the current STATUS.md** so you know which sections exist and the writing voice.

2. **Gather raw signal** in this order:
   - `git log --oneline -30` — recent commits
   - `git status --short` — uncommitted work in progress
   - `gh pr list --state all --limit 10` — recent PRs (skip if `gh` isn't authenticated)
   - Open `TODO` / `FIXME` / `HACK` comments across the stack:
     `grep -rn --include='*.py' --include='*.cs' --include='*.ts' --include='*.tsx' -E 'TODO|FIXME|HACK' . | head -30`

3. **Diff signal against the doc.** Classify each commit since the stamp date as:
   - **Landed feature** → "Recently landed"
   - **Bug fix / doc tweak** → usually skip unless it surfaces a debugging lesson
   - **WIP** → "What's next" or "Open issues"

4. **Propose the edit, don't blindly write it.** Output a diff-style preview of what you'd
   add/move/remove. Ask the user to confirm before applying.

5. **Update `**Last updated:**`** to today's date when you apply changes.

## Guardrails

- **Don't lose the existing voice.** Match STATUS.md's opinionated first-person plural.
- **Keep it under ~120 lines.** Fold old "Recently landed" items into a "## Archive"
  section at the bottom, or trim them.
- **Don't paraphrase commit messages verbatim.** STATUS.md sentences explain *why this
  matters* for the next person picking up work, not what changed line-by-line.

## Why this command exists

STATUS.md only works if it stays fresh. The mechanical "what landed since the doc was
stamped" diff is bookkeeping; the *judgment* is which commits matter and how to phrase
them. This command does the bookkeeping so your attention goes to the judgment.
