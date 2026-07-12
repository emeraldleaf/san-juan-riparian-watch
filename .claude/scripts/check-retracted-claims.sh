#!/usr/bin/env bash
# Semantic drift gate: a retracted claim may only appear in a document that retracts it.
#
# The encoding loop already enforces file SHAPE — canon size, diagram pairing, stale refs after a
# git mv. None of that can catch a document asserting a result that another document has already
# withdrawn. That is not hypothetical: on 2026-07-12 the RF-beats-OlmoEarth result was retracted in
# docs/olmoearth-vs-rf-baseline.md while docs/engineering-review.html — the flagship page on the
# PUBLIC site — went on presenting it as a headline win/lose stat, defended by reasoning that had
# also been disproved. Every mechanical check passed.
#
# Reads the table in docs/RETRACTIONS.md. For each row: any in-scope file matching `pattern` must
# ALSO match `marker` — i.e. it may say the retracted thing only in order to retract it.
#
# Usage: .claude/scripts/check-retracted-claims.sh
# Exit:  0 = clean · 1 = a doc states a retracted claim without retracting it
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

REG="docs/RETRACTIONS.md"
[[ -f "$REG" ]] || { echo "no $REG — nothing to enforce"; exit 0; }

if [[ -t 1 ]]; then RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'
else RED=""; GREEN=""; NC=""; fi

# In-scope docs. Excludes the registry itself (it necessarily quotes every pattern).
# NB: no `mapfile` — macOS ships bash 3.2, where it does not exist, and this script must run
# identically on a laptop and on the CI runner or it is not a gate.
FILES=()
while IFS= read -r line; do
    FILES+=("$line")
done < <(git ls-files --cached --others --exclude-standard 'docs' 'README.md' 'CLAUDE.md' 'CONTEXT.md' \
    | grep -Ev '^docs/RETRACTIONS\.md$' \
    | grep -E '\.(md|html)$')

fails=0
rows=0

# Parse the fenced table rows: | id | `patterns` | `markers` | note |
#
# Alternatives inside a cell are separated by `;`, NOT `|`. This is a markdown table, so `|` is the
# column separator: a regex written `a\|b` gets split across columns and the rule silently matches
# nothing. That happened on the first cut of this script — it passed a file it should have failed.
# A gate that reports "clean" while missing the thing it exists to catch is worse than no gate.
while IFS='|' read -r _ id patterns markers _rest; do
    id="$(echo "$id" | xargs)"
    [[ -z "$id" || "$id" == "id" || "$id" =~ ^-+$ ]] && continue
    # strip the backticks the table uses for readability, then `;` -> regex alternation
    patterns="$(echo "$patterns" | xargs | sed 's/^`//; s/`$//')"
    markers="$(echo "$markers"  | xargs | sed 's/^`//; s/`$//')"
    [[ -z "$patterns" || -z "$markers" ]] && continue
    pattern="$(echo "$patterns" | sed 's/;/|/g')"
    marker="$(echo "$markers"  | sed 's/;/|/g')"
    rows=$((rows + 1))

    for f in "${FILES[@]}"; do
        [[ -f "$f" ]] || continue
        if grep -qE "$pattern" "$f" 2>/dev/null; then
            if ! grep -qiE "$marker" "$f" 2>/dev/null; then
                echo "${RED}✗${NC} ${f}"
                echo "    states the retracted claim '${id}' but does not retract it."
                echo "    matched: $(grep -oE "$pattern" "$f" | sort -u | head -3 | tr '\n' ' ')"
                echo "    fix: state the retraction (must match /${marker}/i), or remove the claim."
                fails=$((fails + 1))
            fi
        fi
    done
done < <(sed -n '/<!-- RETRACTIONS:BEGIN -->/,/<!-- RETRACTIONS:END -->/p' "$REG" | grep '^|')

if [[ "$fails" -gt 0 ]]; then
    echo ""
    echo "${RED}✗ ${fails} document(s) state a retracted claim without retracting it.${NC}"
    echo "  A retraction that lives in only one document is not a retraction."
    exit 1
fi
echo "${GREEN}✓${NC} no document states a retracted claim un-retracted (${rows} retraction(s), ${#FILES[@]} docs)"
