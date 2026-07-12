#!/usr/bin/env bash
# Merge gate: is CodeRabbit's REVIEW green on this PR's CURRENT head?
#
# Not the same question as "is the CodeRabbit check green". The check going green only means
# CodeRabbit *ran*. It can run clean and still have left blocking findings, and — the real
# trap — it can be green against an OLDER commit than the one you are about to merge. A
# reviewer that never saw your last push has not reviewed your PR.
#
# This exists because CodeRabbit's review on PR #5 caught a live SQL-injection weakening that
# CI, SonarQube, 20 unit tests and a careful human all waved through: MvtTileSql validated
# layer names with `^[a-z_]+$`, but in .NET `$` ALSO matches immediately before a trailing
# newline, so "wetlands\n" satisfied it and was interpolated into the SQL literal.
#
# Usage:  ./dev.sh --review-status <PR>     (or:  .claude/scripts/check-coderabbit.sh <PR>)
# Exit:   0 = safe to merge · 1 = do NOT merge · 2 = usage/tooling error
set -uo pipefail

PR="${1:-}"
if [[ -z "$PR" ]]; then
    echo "usage: check-coderabbit.sh <pr-number>" >&2
    exit 2
fi
command -v gh >/dev/null 2>&1 || { echo "gh CLI not found" >&2; exit 2; }

# Colour only when attached to a terminal — this runs in CI and in pipes, where raw escape
# codes are noise (and make the output hard to grep).
if [[ -t 1 ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; NC=""
fi
fail() { echo "${RED}✗ DO NOT MERGE${NC} — $1"; exit 1; }

HEAD=$(gh pr view "$PR" --json headRefOid --jq '.headRefOid' 2>/dev/null) || exit 2
[[ -n "$HEAD" ]] || fail "PR #$PR not found"
SHORT="${HEAD:0:7}"
echo "PR #$PR — head ${SHORT}"

# 1. The check must have RUN on THIS head (not an ancestor).
CHECK=$(gh api "repos/{owner}/{repo}/commits/$HEAD/check-runs" \
    --jq '[.check_runs[] | select(.name|test("coderabbit";"i"))] | last | .conclusion // "pending"' 2>/dev/null)
case "$CHECK" in
    success)  echo "  ${GREEN}✓${NC} CodeRabbit check: success (on ${SHORT})" ;;
    pending|null|"") fail "CodeRabbit has not finished on ${SHORT} — wait for it." ;;
    *)        fail "CodeRabbit check = ${CHECK} on ${SHORT}." ;;
esac

# 2. Unaddressed review findings block the merge, even with a green check.
#    Top-level comments only (in_reply_to_id == null); a thread we replied in is engaged-with.
FINDINGS=$(gh api "repos/{owner}/{repo}/pulls/$PR/comments" --paginate \
    --jq '[.[] | select(.user.login|test("coderabbit";"i")) | select(.in_reply_to_id == null)] | length' 2>/dev/null || echo 0)

# 3. Did CodeRabbit review THIS head? A review on an older commit has not seen your fix.
REVIEW=$(gh api "repos/{owner}/{repo}/pulls/$PR/reviews" --paginate \
    --jq --arg h "$HEAD" '[.[] | select(.user.login|test("coderabbit";"i"))] | last
         | if . == null then "none" elif .commit_id == $h then "current:\(.state)" else "stale" end' 2>/dev/null)

if [[ "$FINDINGS" -gt 0 ]]; then
    case "$REVIEW" in
        current:APPROVED)
            echo "  ${GREEN}✓${NC} ${FINDINGS} finding(s), and CodeRabbit re-reviewed ${SHORT} and APPROVED"
            ;;
        current:*)
            fail "${FINDINGS} finding(s); CodeRabbit's review on ${SHORT} is ${REVIEW#current:}, not APPROVED."
            ;;
        stale)
            fail "${FINDINGS} finding(s), and CodeRabbit's last review predates ${SHORT}. Push the fix and let it re-review."
            ;;
        *)
            fail "${FINDINGS} unaddressed CodeRabbit finding(s) on #$PR."
            ;;
    esac
else
    echo "  ${GREEN}✓${NC} no CodeRabbit findings"
    [[ "$REVIEW" == "stale" ]] && echo "  ${YELLOW}!${NC} last review predates ${SHORT} (no findings, so not blocking)"
fi

# 4. And the rest of the gates, so this is one command instead of three.
read -r MERGEABLE STATE < <(gh pr view "$PR" --json mergeable,mergeStateStatus \
    --jq '"\(.mergeable) \(.mergeStateStatus)"')
[[ "$MERGEABLE" == "MERGEABLE" ]] || fail "PR is ${MERGEABLE} (conflicts?)"

FAILED=$(gh pr view "$PR" --json statusCheckRollup \
    --jq '[.statusCheckRollup[]? | select(.conclusion != null and .conclusion != "SUCCESS" and .conclusion != "NEUTRAL" and .conclusion != "SKIPPED") | .name] | join(", ")')
[[ -z "$FAILED" ]] || fail "failing checks: ${FAILED}"

echo "  ${GREEN}✓${NC} mergeable, all checks green"
echo "${GREEN}✓ SAFE TO MERGE${NC} — PR #$PR"
