#!/usr/bin/env bash
# PostToolUse hook helper. Reads the tool-call JSON on stdin; if the edited file is the
# repo-root CLAUDE.md, prints a list of files containing the marker "See CLAUDE.md"
# (excluding CLAUDE.md itself) as additionalContext for the assistant.
#
# The list represents files that paraphrase a CLAUDE.md rule and may need review when the
# canonical rule changes. Convention documented in CONTEXT.md "Greppable paraphrases".
#
# Ported from the NextAurora encoding-loop method. Repo root is derived from this script's
# own location so it survives the project path containing spaces.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Extract the edited file path from the tool-call payload. Empty if jq fails or missing.
file=$(jq -r '.tool_input.file_path // ""' 2>/dev/null)

# Only act when the edited file's basename is CLAUDE.md (case-insensitive — macOS FS also
# resolves claude.md to the same file). Anything else: silent no-op.
base=$(basename "$file" 2>/dev/null | tr '[:upper:]' '[:lower:]')
if [ "$base" != "claude.md" ]; then
    exit 0
fi

# Find files with the cross-reference marker, excluding CLAUDE.md/claude.md itself.
matches=$(grep -rln "See CLAUDE.md" \
    --include='*.py' --include='*.cs' --include='*.ts' --include='*.tsx' \
    --include='*.sql' --include='*.md' --include='*.yaml' --include='*.yml' \
    "$REPO_ROOT" 2>/dev/null \
    | grep -iv "/claude\.md$" \
    || true)

# No matches: silent no-op.
if [ -z "$matches" ]; then
    exit 0
fi

msg=$(printf 'CLAUDE.md was edited. Files containing the "See CLAUDE.md" marker (review each for staleness against the new rule):\n%s' "$matches")
jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
