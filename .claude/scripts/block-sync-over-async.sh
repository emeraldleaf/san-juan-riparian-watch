#!/usr/bin/env bash
# PreToolUse hook. Blocks proposed Edit/Write tool calls that introduce sync-over-async
# patterns in .cs files. The build-time net (Microsoft.CodeAnalysis.BannedApiAnalyzers +
# BannedSymbols.txt) catches the same patterns at compile, but at that point the bad code
# is already in the file. This hook stops it at *propose* time so the diff never lands.
#
# Patterns blocked:
#   .Result            blocking on a Task
#   .Wait()            blocking on a Task
#   .GetAwaiter().GetResult()   the third common spelling
#
# Rationale: CLAUDE.md "Performance Rules" — "Async on request paths: await everywhere.
# Never .Result, .Wait(), or .GetAwaiter().GetResult()." See CLAUDE.md.
#
# Exit codes:
#   0  allow the tool call (default)
#   2  block (deny output is emitted as JSON)

set -uo pipefail

# Read the entire tool-call JSON from stdin.
payload=$(cat)

# Extract relevant fields. file_path tells us *what* file; the proposed content lives in
# different keys depending on the tool: new_string for Edit, content for Write.
file=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
tool=$(printf '%s' "$payload" | jq -r '.tool_name // ""' 2>/dev/null)

# Only inspect .cs files. Anything else is silently allowed.
case "$file" in
    *.cs) ;;
    *) exit 0 ;;
esac

# Pull the proposed text. Edit gives us a single new_string; Write gives content.
# replace_all edits are still single old_string/new_string pairs from the hook's view.
case "$tool" in
    Edit)
        proposed=$(printf '%s' "$payload" | jq -r '.tool_input.new_string // ""' 2>/dev/null)
        ;;
    Write)
        proposed=$(printf '%s' "$payload" | jq -r '.tool_input.content // ""' 2>/dev/null)
        ;;
    *)
        exit 0
        ;;
esac

# Strip single-line comments before pattern matching so a comment that *mentions* .Result
# (e.g. an explanation, or this very script) doesn't trigger a false positive. We don't
# need a real C# tokenizer here — the // strip is good enough for hook-time triage.
stripped=$(printf '%s' "$proposed" | sed 's://.*::g')

# Pattern matchers. Each is a fixed-string grep (-F) so we don't fight regex escaping.
violations=""
if printf '%s' "$stripped" | grep -F -q '.Result'; then
    # .Result is the noisiest match because EF Core uses .Result on IQueryable etc.
    # Narrow it: only complain when .Result follows what looks like a Task-returning
    # method call — heuristic: ").Result" or "Async.Result" patterns.
    if printf '%s' "$stripped" | grep -E -q '(Async\.Result|\)\.Result)'; then
        violations="${violations}  - .Result on a Task (block; use 'await' instead)\n"
    fi
fi
if printf '%s' "$stripped" | grep -F -q '.Wait()'; then
    violations="${violations}  - .Wait() on a Task (block; use 'await' instead)\n"
fi
if printf '%s' "$stripped" | grep -F -q '.GetAwaiter().GetResult()'; then
    violations="${violations}  - .GetAwaiter().GetResult() (block; use 'await' instead)\n"
fi

# No violations: allow silently.
if [ -z "$violations" ]; then
    exit 0
fi

# Block with a clear reason. The JSON shape is the documented PreToolUse deny output.
reason=$(printf 'Sync-over-async blocked in %s:\n%bSee CLAUDE.md "Performance Rules" — async on request paths must await everywhere. The same patterns are banned at build time via BannedSymbols.txt; this hook catches them earlier.' "$file" "$violations")
jq -n --arg r "$reason" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
exit 2
