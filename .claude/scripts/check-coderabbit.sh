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

# 0. A SKIPPED review must never read as green. THIS IS THE ONE THAT BIT US.
#
#    CodeRabbit posts a SUCCESS check even when it skips the review (e.g. a label filter did not
#    match). This script used to trust that check and then count inline comments — and a skipped
#    review has zero comments, so it reported "✓ no CodeRabbit findings" and waved the PR through.
#
#    25 of the first 29 merged PRs were skipped that way. Every one of them passed this gate. The
#    gate was theatre, and it was reporting "clean" — which is worse than having no gate at all,
#    because it bought confidence that nothing had earned.
#
#    So: look for the skip notice FIRST, and fail on it.
SKIPPED=$(gh api "repos/{owner}/{repo}/issues/$PR/comments" --paginate \
    --jq '[.[] | select(.user.login|test("coderabbit";"i")) | select(.body|test("Review skipped"))] | length' 2>/dev/null || echo 0)
if [[ "${SKIPPED:-0}" -gt 0 ]]; then
    fail "CodeRabbit SKIPPED this PR (it says so in a comment) — yet its check may still be green.
    A skipped review is not a review. Check .coderabbit.yaml for a label/title filter, or comment
    '@coderabbitai review' to trigger one."
fi

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
    # "No findings" is only meaningful if a review ACTUALLY HAPPENED. Absence of findings and
    # absence of a review look identical from the outside — and that is exactly how 25 PRs were
    # waved through. Demand positive evidence that CodeRabbit looked at THIS head.
    case "$REVIEW" in
        current:*)
            echo "  ${GREEN}✓${NC} CodeRabbit reviewed ${SHORT} (${REVIEW#current:}) — no findings"
            ;;
        stale)
            fail "no findings, but CodeRabbit's last review PREDATES ${SHORT}. It has not seen this code.
    'No findings' from a review that never ran is not a pass."
            ;;
        *)
            fail "CodeRabbit has NOT reviewed this PR at all (no review on any commit).
    A green check is not a review — CodeRabbit posts one even when it skips. Trigger a review with
    '@coderabbitai review', or check .coderabbit.yaml for a filter that is excluding this PR."
            ;;
    esac
fi

# 4. And the rest of the gates, so this is one command instead of three.
read -r MERGEABLE STATE < <(gh pr view "$PR" --json mergeable,mergeStateStatus \
    --jq '"\(.mergeable) \(.mergeStateStatus)"')
[[ "$MERGEABLE" == "MERGEABLE" ]] || fail "PR is ${MERGEABLE} (conflicts?)"

# A check that has not COMPLETED is pending, not failing. Judging it by `conclusion` alone
# reports an in-flight job as a failure — which is worse than useless: a gate that cries wolf
# is a gate people learn to bypass. (Observed on #18: `python` was still resolving and the gate
# said "failing checks: python"; it went green moments later.) Distinguish the two, and say
# "wait" rather than "do not merge".
ROLLUP=$(gh pr view "$PR" --json statusCheckRollup --jq '.statusCheckRollup')

PENDING=$(jq -r '[.[]? | select((.status // "COMPLETED") != "COMPLETED") | (.name // .context)] | join(", ")' <<<"$ROLLUP")
if [[ -n "$PENDING" ]]; then
    echo "  ${YELLOW}…${NC} still running: ${PENDING}"
    echo "${YELLOW}⧗ NOT YET${NC} — checks have not finished on ${SHORT}. Re-run when they do."
    exit 1
fi

FAILED=$(jq -r '[.[]? | select(.conclusion != null and .conclusion != "SUCCESS" and .conclusion != "NEUTRAL" and .conclusion != "SKIPPED") | (.name // .context)] | join(", ")' <<<"$ROLLUP")
[[ -z "$FAILED" ]] || fail "failing checks: ${FAILED}"

echo "  ${GREEN}✓${NC} mergeable, all checks green"
echo "${GREEN}✓ SAFE TO MERGE${NC} — PR #$PR"
