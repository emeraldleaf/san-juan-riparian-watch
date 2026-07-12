# Code review — the merge gate

**A PR does not merge until CodeRabbit's *review* is green on the PR's current head.**

Run the gate:

```bash
./dev.sh --review-status <PR>     # exit 0 = safe to merge, 1 = do not merge
```

See CLAUDE.md.

## The check is not the review

These are different questions, and conflating them is how a bad merge happens:

| | What it tells you |
|---|---|
| **CodeRabbit check = success** | CodeRabbit *ran*. That's all. |
| **CodeRabbit review = APPROVED on this head** | CodeRabbit *looked at the code you are about to merge* and had nothing blocking. |

A green check is compatible with all of these:

- CodeRabbit left blocking findings and you never addressed them.
- CodeRabbit reviewed commit `abc123`, you then pushed `def456` — **the reviewer never saw your
  last push.** A stale approval is not an approval.
- You "fixed" the findings but never let it re-review, so nothing confirms the fix is right.

`./dev.sh --review-status` fails on all three. It checks, in order: the check ran **on this exact
head**; there are no unaddressed top-level findings (or, if there are, that CodeRabbit
**re-reviewed this head and approved**); the PR is mergeable; and every other check is green.

## Why this gate exists

It is not ceremony. On **PR #5**, CodeRabbit caught a live SQL-injection weakening that **every
other gate passed** — CI, SonarQube, 20 unit tests, and a careful human review:

```csharp
Regex.IsMatch(layer, "^[a-z_]+$")   // looks strict. It isn't.
```

`MvtTileSql.Build()` interpolates the layer name into a single-quoted SQL literal, so this regex
is the only thing standing between a caller and the query text. But **in .NET, `$` also matches
immediately before a trailing newline.** So `"wetlands\n"` satisfies `^[a-z_]+$` — and with it,
anything smuggled onto the following line.

The fix is `\A[a-z_]+\z`, which anchors to the absolute end of input and admits no trailing
newline. It is pinned by `MvtTileSqlTests.Build_RejectsLayerWithTrailingNewline` — and that test
was *verified to fail* against the old anchors before the fix landed, rather than assumed to.

The lesson generalises: the gates that pass are not evidence. A reviewer looking from a different
angle than yours is worth waiting for.

## When CodeRabbit leaves findings

1. **Fix them.** If you disagree, say so in the thread — a reply marks it engaged-with rather
   than ignored.
2. **Push the fix.**
3. **Let it re-review the fix commit.** This is the step people skip; a green check on the *old*
   commit means nothing about the new one.
4. Re-run `./dev.sh --review-status <PR>`.

Do not merge on a green check while findings sit unaddressed — that is the exact failure this
gate exists to prevent.

## The three tiers

| Tier | Surface | Catches |
|---|---|---|
| 1 | `CLAUDE.md`, `.claude/` agents + commands | Convention drift, at authoring time |
| 2 | **CodeRabbit** (`.coderabbit.yaml` path rules) | Semantic and security defects, at review time |
| 3 | **SonarQube** (`./dev.sh --lint`) + CI | Static analysis, tests, lint |

Tier 2 is the only one that reads the change *as a change* — with intent, in context. It is the
tier that caught the regex.
