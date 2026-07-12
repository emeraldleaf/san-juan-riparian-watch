#!/usr/bin/env bash
# Reachability gate: every spec and ADR must be linked from the published hub.
#
# A document nobody can reach is a document nobody reads. docs/index.md is the GitHub Pages hub —
# the only navigation the public site has. On 2026-07-12 it linked 4 of 6 ADRs; the newest one
# (the OlmoEarth fine-tune decision, i.e. the plan of record) was live on the site but reachable
# only by guessing its URL. No existing check noticed, because they all enforce file shape rather
# than reachability.
#
# Usage: .claude/scripts/check-doc-orphans.sh
# Exit:  0 = every spec/ADR is linked · 1 = orphans
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

HUB="docs/index.md"
[[ -f "$HUB" ]] || { echo "no $HUB — nothing to enforce"; exit 0; }

if [[ -t 1 ]]; then RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'
else RED=""; GREEN=""; NC=""; fi

orphans=0
checked=0
for f in docs/specs/*.md docs/decisions/*.md docs/audits/*.md; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    # An audit is reachable via the falsification log (docs/audits/README.md), which is itself
    # linked from the hub — so check audits against the log, and everything else against the hub.
    # An unreachable audit is the same failure as an unreachable ADR: written, then invisible.
    index="$HUB"
    case "$f" in
        docs/audits/*)
            [[ "$base" == "README.md" ]] && continue   # the log itself; it is linked from the hub
            index="docs/audits/README.md"
            ;;
    esac
    checked=$((checked + 1))
    # Jekyll rewrites .md -> .html, so accept either spelling.
    if ! grep -qF "${base}" "$index" && ! grep -qF "${base%.md}.html" "$index"; then
        echo "${RED}✗${NC} orphan: ${f}"
        echo "    published to Pages but not linked from ${index} — reachable only by guessing the URL."
        orphans=$((orphans + 1))
    fi
done

if [[ "$orphans" -gt 0 ]]; then
    echo ""
    echo "${RED}✗ ${orphans} orphaned doc(s).${NC} Add them to ${HUB}, under Decisions or Specs."
    exit 1
fi
echo "${GREEN}✓${NC} all ${checked} specs/ADRs are linked from ${HUB}"
