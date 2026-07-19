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
#    Use the LATEST signal, not the mere presence of an old one: a PR can be skipped first and then
#    reviewed on demand ('@coderabbitai review'), and the stale skip notice must not veto that.
#    Equally, CodeRabbit does NOT create a formal review object when it finds nothing — it only
#    comments. So "did it review?" is answered by its comments, not by the reviews API.
STATUS=$(gh api "repos/{owner}/{repo}/issues/$PR/comments" --paginate \
    --jq '[.[] | select(.user.login|test("coderabbit";"i"))
             | select(.body|test("Review skipped|Review finished|Actionable comments posted"))
             | if (.body|test("Review skipped")) then "skipped" else "reviewed" end] | last // "none"' \
    2>/dev/null || echo none)

case "$STATUS" in
    reviewed)
        echo "  ${GREEN}✓${NC} CodeRabbit reviewed this PR"
        ;;
    skipped)
        fail "CodeRabbit SKIPPED this PR — and its check is green anyway.
    A skipped review is not a review, and 'no findings' from a review that never ran is not a pass.
    Check .coderabbit.yaml for a label/title filter, or comment '@coderabbitai review'."
        ;;
    *)
        fail "CodeRabbit has posted NOTHING on this PR — no review, no skip notice.
    A green check is not a review; it posts one even when it skips. Wait, or trigger it with
    '@coderabbitai review'."
        ;;
esac

# 1. Did CodeRabbit read THIS head — not an ancestor of it?
#
#    This USED to assert a green `coderabbit` CHECK-RUN on the head. That was wrong in both
#    directions, and it is the second time this gate has been wrong about its own evidence:
#
#      TOO WEAK  — a check-run only proves CodeRabbit *ran*. It says nothing about WHICH commit it
#                  read. That is the whole question a merge gate exists to answer.
#      TOO STRONG— CodeRabbit emits NO check-run for an on-demand review ('@coderabbitai review').
#                  So the gate demanded a signal that would never arrive and blocked, forever, on
#                  four PRs it had in fact fully reviewed with zero findings.
#
#    A gate that blocks forever is not "safe". It is a gate people learn to bypass — which is how
#    you end up merging unreviewed code with a clean conscience.
#
#    The honest evidence is CodeRabbit's own walkthrough, which states the commit range it read:
#    "Files that changed ... between <base-sha> and <head-sha>". If the CURRENT head appears there,
#    CodeRabbit has seen the code we are about to merge. That is strictly stronger than the check.
#
#    Beware the sibling trap: an on-demand review replies "✅ Review finished" even when it did
#    nothing ("does not re-review already reviewed commits"). Never take that reply as evidence.
#    Only the head SHA appearing in a walkthrough counts.
REVIEWED_HEAD=$(gh api "repos/{owner}/{repo}/issues/$PR/comments" --paginate \
    --jq '.[] | select(.user.login|test("coderabbit";"i")) | .body' 2>/dev/null \
    | grep -oiE '\b[0-9a-f]{40}\b' | grep -Fxc "$HEAD" || true)

if [[ "${REVIEWED_HEAD:-0}" -gt 0 ]]; then
    echo "  ${GREEN}✓${NC} CodeRabbit's walkthrough names ${SHORT} — it read this exact head"
else
    fail "CodeRabbit has not reviewed ${SHORT}.
    Its walkthrough does not name this commit, so it has not seen what you are about to merge.
    Push, or trigger it with '@coderabbitai review' — and do NOT trust a bare '✅ Review finished'."
fi

# 2. Unaddressed review findings block the merge, even with a green check.
#    Top-level comments only (in_reply_to_id == null); a thread we replied in is engaged-with.
FINDINGS=$(gh api "repos/{owner}/{repo}/pulls/$PR/comments" --paginate \
    --jq '[.[] | select(.user.login|test("coderabbit";"i")) | select(.in_reply_to_id == null)] | length' 2>/dev/null || echo 0)

# 3. Did CodeRabbit review THIS head? A review on an older commit has not seen your fix.
#    NOTE: `gh api --jq` does NOT accept jq's `--arg`; passing it makes gh error ("accepts 1
#    arg(s), received 4"), so REVIEW came back EMPTY and every findings-bearing PR fell through
#    to the "*)" case as "unaddressed" — even ones CodeRabbit had APPROVED on the head. It
#    false-negatived #61 (approved) and stalled the merge poller. Pipe to real `jq`, which does
#    support `--arg` (and matches the `jq` usage further down). `--paginate` merges the array.
REVIEW=$(gh api "repos/{owner}/{repo}/pulls/$PR/reviews" --paginate 2>/dev/null \
    | jq -r --arg h "$HEAD" '[.[] | select(.user.login|test("coderabbit";"i"))] | last
         | if . == null then "none" elif .commit_id == $h then "current:\(.state)" else "stale" end')

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
    # A review DID happen (established above); it simply found nothing.
    echo "  ${GREEN}✓${NC} no CodeRabbit findings"
    [[ "$REVIEW" == "stale" ]] && \
        echo "  ${YELLOW}!${NC} its formal review object predates ${SHORT} (no findings, not blocking)"
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
