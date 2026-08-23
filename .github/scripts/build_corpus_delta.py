#!/usr/bin/env python3
"""Turn a `git diff --name-status -M` into the corpus delta payload.

The public repo is the only side that can compute what changed (it owns the history),
so it does, and the harness applies the result. Schema + guarantees:
``docintel/CORPUS_DELTA_CONTRACT.md``.

Maps repo paths to the corpus ids the index actually stores, because those are what a
delete has to target: ``docs/specs/x.md`` is indexed as ``project-x.md``, and a delete
by any other name silently leaves the old chunks in place, still citable.

Usage:
    build_corpus_delta.py <name-status-file> <from-sha> <to-sha>   # JSON to stdout
"""

from __future__ import annotations

import json
import os
import sys

# Only these become corpus documents. seed_sources.yaml is watched for CHANGES (a new
# external source means a full sync is safer than a delta) but is not itself indexed.
_CORPUS_ROOTS = ("docs/",)
_CORPUS_FILES = ("CLAUDE.md", "CONTEXT.md")
_SEED = "docintel/corpus/seed_sources.yaml"


def corpus_id(path: str) -> str | None:
    """Repo path -> the `source_file` the index stores, or None if not indexed.

    Ids are flat (`project-<basename>.md`) regardless of subdirectory: the index has no
    notion of docs/specs vs docs/decisions, so `project-` + basename is the whole key.
    """
    if not path.endswith(".md"):
        return None
    if path in _CORPUS_FILES:
        return f"project-{os.path.basename(path)}"
    if path.startswith(_CORPUS_ROOTS):
        return f"project-{os.path.basename(path)}"
    return None


def main() -> int:
    diff_file, sha_from, sha_to = sys.argv[1], sys.argv[2], sys.argv[3]
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    seed_touched = False

    with open(diff_file, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            status, paths = parts[0], parts[1:]
            if _SEED in paths:
                seed_touched = True
            # A rename is a delete of the old id plus an add of the new one: the chunks
            # are stored under the OLD source_file and nothing else will remove them.
            if status.startswith("R") and len(paths) == 2:
                old_id, new_id = corpus_id(paths[0]), corpus_id(paths[1])
                if old_id:
                    deleted.append(old_id)
                if new_id:
                    added.append(new_id)
                continue
            cid = corpus_id(paths[0])
            if not cid:
                continue
            if status.startswith("A"):
                added.append(cid)
            elif status.startswith("D"):
                deleted.append(cid)
            else:  # M, and anything else that means "content changed"
                modified.append(cid)

    # A changed seed list can add or drop EXTERNAL sources, which this diff cannot see.
    # Escalate to a full sync rather than pretend the delta is complete.
    if seed_touched:
        print(json.dumps({"mode": "full", "reason": "seed_sources.yaml changed",
                          "from": sha_from, "to": sha_to}))
        return 0

    payload = {
        "mode": "delta",
        "from": sha_from,
        "to": sha_to,
        "added": sorted(set(added)),
        "modified": sorted(set(modified)),
        "deleted": sorted(set(deleted) - set(added)),  # a rename round-trip is a no-op
    }
    # Nothing indexed changed (e.g. only a diagram or a non-md file moved).
    if not (payload["added"] or payload["modified"] or payload["deleted"]):
        payload["mode"] = "noop"
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
