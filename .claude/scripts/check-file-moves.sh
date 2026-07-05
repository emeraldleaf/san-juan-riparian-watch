#!/usr/bin/env bash
# PostToolUse hook on Bash. When the command is `git mv` or `git rm`, finds the source
# path(s) and greps the repo for refs to them. Prints findings as additionalContext so the
# model sees the worklist in the same session the move happened.
#
# Purpose: catch doc/comment/Dockerfile/SQL-migration drift in the same session a file gets
# moved or deleted. Restricted to git-tracked operations (not plain mv/rm) to cut
# false-positive noise from temp files and build artifacts.
#
# Ported from the NextAurora encoding-loop method. See CONTEXT.md "File-move discipline".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

command=$(jq -r '.tool_input.command // ""' 2>/dev/null)

# Only fire on git mv / git rm. Plain mv/rm is too noisy.
case "$command" in
    *"git mv "*) ;;
    *"git rm "*) ;;
    *) exit 0 ;;
esac

old_paths=()

# git mv <src> <dst> — capture the FIRST positional arg (the source).
if [[ "$command" =~ git[[:space:]]+mv[[:space:]]+([^[:space:]]+) ]]; then
    src="${BASH_REMATCH[1]}"
    case "$src" in
        -*) ;;  # skip if it looked like a flag
        *) old_paths+=("$src") ;;
    esac
fi

# git rm [flags] <path>... — capture all non-flag tokens after `git rm`.
if [[ "$command" =~ git[[:space:]]+rm[[:space:]] ]]; then
    args=$(echo "$command" | sed -E 's/^.*git[[:space:]]+rm[[:space:]]+//' | tr -s ' ')
    for token in $args; do
        case "$token" in
            -*) continue ;;
            "") continue ;;
            *) old_paths+=("$token") ;;
        esac
    done
fi

# Nothing to do.
if [ ${#old_paths[@]} -eq 0 ]; then
    exit 0
fi

# For each old path, grep for refs. --fixed-strings so paths with dots/slashes match
# literally instead of as regex.
findings=""
for old_path in "${old_paths[@]}"; do
    case "$old_path" in
        ""|"*"|"."|"./"|".."|"./*") continue ;;
    esac

    matches=$(grep -rln --fixed-strings "$old_path" \
        --include='*.md' --include='*.py' --include='*.cs' --include='*.ts' \
        --include='*.tsx' --include='*.sql' --include='*.yml' --include='*.yaml' \
        --include='*.sh' --include='Dockerfile*' \
        "$REPO_ROOT" 2>/dev/null \
        | head -30 \
        || true)
    if [ -n "$matches" ]; then
        findings+=$(printf "Refs to '%s' still present in:\n%s\n\n" "$old_path" "$matches")
    fi
done

if [ -z "$findings" ]; then
    exit 0
fi

msg=$(printf 'File-move/delete detected. Refs to the OLD path may need updating before commit:\n\n%s\nUpdate the paraphrases in the same PR. See CONTEXT.md "File-move discipline".' "$findings")
jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
