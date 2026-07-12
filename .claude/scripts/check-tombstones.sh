#!/usr/bin/env bash
# Tombstone audit — removed-identifier drift control. See CLAUDE.md.
#
# When a subsystem is removed (a transport, a metric, an API), its identifiers get
# tombstoned in .claude/tombstones.txt. This script fails if any tombstoned pattern
# appears in tracked files outside the allowlist (.claude/tombstones-allowlist.txt).
#
# Why: the compiler catches stale identifiers in code; NOTHING catches them in docs,
# comments, and config. Ported from NovaCraft, where a transport swap left 15+ docs teaching
# the removed system as current. The same thing happened here: the NDVI health thresholds were
# "reconciled" across code, CLAUDE.md and the legend — and the retired >0.3 / 0.15 values sat
# on in a frontend component docstring anyway, because a human sweep is not a gate. The
# completion criterion is "this script passes", not "the docs someone remembered are updated".
#
# Usage: .claude/scripts/check-tombstones.sh   (run from anywhere; CI runs it per PR)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TOMBSTONES=".claude/tombstones.txt"
ALLOWLIST=".claude/tombstones-allowlist.txt"

excludes=()
while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    excludes+=(":(exclude)$line")
done < "$ALLOWLIST"

fail=0
while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    case "$pattern" in \#*) continue ;; esac
    # git grep over tracked files only; -i case-insensitive, -E extended regex.
    # Exit codes: 0 = matches (violation), 1 = clean, >=2 = error (e.g. invalid
    # regex) — an invalid tombstone must FAIL the audit, not silently disable it.
    set +e
    # --untracked: a NEW file is invisible to `git grep` until it is committed, so the gate
    # passed locally and failed in CI on the very PR that added this file. Local must equal CI.
    hits=$(git grep --untracked -inE "$pattern" -- '.' "${excludes[@]}" 2>&1)
    status=$?
    set -e
    if [ "$status" -ge 2 ]; then
        echo "TOMBSTONE AUDIT ERROR — pattern '$pattern' failed to evaluate (git grep exit $status):"
        echo "$hits" | sed -n '1,5p'
        fail=1
    elif [ "$status" -eq 0 ] && [ -n "$hits" ]; then
        echo "TOMBSTONE VIOLATION — pattern '$pattern':"
        # sed -n '1,30p' rather than piping through head: under pipefail, head
        # closing the pipe early would SIGPIPE the producer and abort the script.
        echo "$hits" | sed -n '1,30p' | sed 's/^/  /'
        echo ""
        fail=1
    fi
done < "$TOMBSTONES"

if [ "$fail" -eq 1 ]; then
    echo "Removed identifiers are resurfacing (or were never fully swept)."
    echo "Fix the references — or, for genuinely historical/comparative mentions,"
    echo "add the file to $ALLOWLIST with a justification comment."
    exit 1
fi
echo "Tombstone audit clean."
