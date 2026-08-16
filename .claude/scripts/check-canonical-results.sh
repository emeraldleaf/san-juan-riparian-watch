#!/usr/bin/env bash
# Semantic drift gate: every public-facing doc must carry the CURRENT value of each headline result.
#
# The INVERSE of check-retracted-claims.sh. That gate catches a document *stating a withdrawn claim*;
# this one catches a document *missing a current one* — staleness by omission. Both are the same
# disease: a result living in one doc while another ignores or contradicts it.
#
# It exists because on 2026-08-16 docs/engineering-review.html (the flagship public page) still ended
# section 06 with "the fine-tuned OlmoEarth test doesn't exist yet, don't cite this as FM evidence" —
# 15 days after the leave-one-reach-out result (arroyo 0.557 -> 0.889) was measured and headlined on
# the live site. Every shape check passed; the retraction gate passed (nothing was contradicted); the
# page was simply stale. Nothing was looking for a MISSING result. This does.
#
# Reads the table in docs/canonical-results.md. For each row: every file in `must-appear-in` must
# contain a match for `value` (an extended regex).
#
# Usage: .claude/scripts/check-canonical-results.sh
# Exit:  0 = clean · 1 = a listed doc is missing a current result · 2 = setup error
#
# NB: no `mapfile` and no `xargs` on the regex cell — macOS ships bash 3.2 (no mapfile) and xargs
# eats the backslash in `0\.889`. Trim with sed so the regex survives. This must run identically on a
# laptop and the CI runner or it is not a gate.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

REG="docs/canonical-results.md"
[[ -f "$REG" ]] || { echo "no $REG — nothing to enforce"; exit 0; }

if [[ -t 1 ]]; then RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'
else RED=""; GREEN=""; NC=""; fi

trim() { sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/^`//; s/`$//'; }

fails=0
rows=0

# Parse the fenced table rows: | id | `value` | `file;file` | note |
# Files inside a cell are separated by `;`, NOT `|` (the column separator).
while IFS='|' read -r _ id value files _rest; do
    id="$(printf '%s' "$id" | trim)"
    [[ -z "$id" || "$id" == "id" || "$id" =~ ^-+$ ]] && continue
    value="$(printf '%s' "$value" | trim)"
    files="$(printf '%s' "$files" | trim)"
    [[ -z "$value" || -z "$files" ]] && continue
    rows=$((rows + 1))
    files="${files//;/ }"   # repo paths have no spaces; split on whitespace
    for f in $files; do
        [[ -z "$f" ]] && continue
        if [[ ! -f "$f" ]]; then
            echo "${RED}MISSING FILE${NC} [$id] $f — listed in $REG but not in the repo"
            fails=$((fails + 1)); continue
        fi
        if ! grep -Eq -- "$value" "$f"; then
            echo "${RED}STALE${NC} [$id] $f is missing the current value /${value}/"
            fails=$((fails + 1))
        fi
    done
done < "$REG"

if [[ "$fails" -gt 0 ]]; then
    echo "${RED}✗ canonical-results: $fails miss(es) across $rows result(s) — a public doc is stale.${NC}"
    echo "  Fix: update the doc to the current value, or edit $REG if the result itself changed."
    exit 1
fi
echo "${GREEN}✓ canonical-results: all $rows headline result(s) present in every listed doc.${NC}"
exit 0
