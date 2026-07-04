#!/usr/bin/env bash
# SessionStart hook. Surfaces the top of docs/STATUS.md so the assistant starts each
# session knowing where the project is and what's next, instead of cold-reading the repo.
#
# Ported from the NextAurora encoding-loop method. Repo root derived from script location
# so it survives the project path containing spaces.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATUS="$REPO_ROOT/docs/STATUS.md"

# Silent no-op if STATUS.md is missing (e.g. fresh clone before the doc lands).
if [ ! -f "$STATUS" ]; then
    exit 0
fi

# Header + top section. Cap at 80 lines so we don't flood context on every session start.
snippet=$(head -80 "$STATUS")

branch=$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "(detached)")
last_commit=$(git -C "$REPO_ROOT" log -1 --oneline 2>/dev/null || echo "(no commits)")

msg=$(printf '## Session orientation\n\nBranch: %s\nLast commit: %s\n\n--- docs/STATUS.md (top 80 lines) ---\n%s\n--- end snippet ---\n\nFull STATUS.md at docs/STATUS.md. Update it at the start or end of each working session per CLAUDE.md.' "$branch" "$last_commit" "$snippet")

jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $m}}'
