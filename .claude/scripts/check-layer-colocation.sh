#!/usr/bin/env bash
# ── Spatial-provenance gate: co-location ─────────────────────────────────────
# Any set of map layers declared a "head-to-head comparison" MUST be co-located —
# their bounding boxes must overlap >= min_iou. This catches the 2026-08-21
# reach-provenance gap, where rf_malpais and fm_malpais were compared as one reach
# but sit ~5 km apart, so the RF-vs-FM "arroyo rescue" was two different places.
#
# Every existing drift gate enforces TEXTUAL consistency; this is the first that
# reaches the pixels. It also SELF-TESTS: it re-runs the exact retracted Malpais
# pairing and fails loudly if that ever stops being flagged (a broken gate is
# worse than none). See docs/2026-08-21-reach-provenance-gap.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MANIFEST="$ROOT/.claude/spatial-provenance.json"
PY="$(command -v python3 || echo python3)"

exec "$PY" - "$MANIFEST" "$ROOT" <<'PYEOF'
import json, sys, os

manifest_path, root = sys.argv[1], sys.argv[2]
if not os.path.exists(manifest_path):
    print(f"✗ spatial-provenance manifest missing: {manifest_path}")
    sys.exit(1)
m = json.load(open(manifest_path))
min_iou = float(m.get("min_iou", 0.5))

def bbox(rel):
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None, f"missing file: {rel}"
    gj = json.load(open(path))
    xs, ys = [], []
    def walk(a):
        if a and isinstance(a[0], (int, float)):
            xs.append(a[0]); ys.append(a[1])
        elif a:
            for x in a: walk(x)
    for f in gj.get("features", []):
        walk((f.get("geometry") or {}).get("coordinates"))
    if not xs:
        return None, f"no coordinates: {rel}"
    return (min(xs), min(ys), max(xs), max(ys)), None

def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2]-a[0]) * (a[3]-a[1])
    ub = (b[2]-b[0]) * (b[3]-b[1])
    union = ua + ub - inter
    return inter / union if union > 0 else 0.0

def min_pair_iou(group):
    """Lowest pairwise bbox IoU in a group, plus per-file errors."""
    boxes, errs = {}, []
    for rel in group["layers"]:
        bb, err = bbox(rel)
        if err: errs.append(err)
        else: boxes[rel] = bb
    if errs:
        return None, errs
    names = list(boxes)
    worst = 1.0; worst_pair = None
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            v = iou(boxes[names[i]], boxes[names[j]])
            if v < worst:
                worst, worst_pair = v, (names[i], names[j])
    return (worst, worst_pair), []

failures = 0

# 1. Declared comparisons: every pair must be co-located.
for g in m.get("comparisons", []):
    res, errs = min_pair_iou(g)
    if errs:
        print(f"✗ {g['name']}: {'; '.join(errs)}"); failures += 1; continue
    worst, pair = res
    if worst < min_iou:
        print(f"✗ {g['name']} ({g.get('reach','')}) — layers are NOT co-located.")
        print(f"    worst pairwise bbox IoU {worst:.3f} < {min_iou} between:")
        print(f"      {os.path.basename(pair[0])}")
        print(f"      {os.path.basename(pair[1])}")
        print(f"    fix: compare layers on the SAME reach, or split into separate comparisons.")
        failures += 1
    else:
        print(f"✓ {g['name']}: co-located (min pairwise IoU {worst:.3f})")

# 2. Self-test: the known-bad pairing MUST still be caught.
for g in m.get("selftest_expected_fail", []):
    res, errs = min_pair_iou(g)
    if errs:
        print(f"✓ selftest {g['name']}: not evaluable ({'; '.join(errs)}) — layers gone, ok")
        continue
    worst, pair = res
    if worst >= min_iou:
        print(f"✗ SELF-TEST BROKEN: {g['name']} was expected to FAIL but passed (IoU {worst:.3f}).")
        print(f"    The gate no longer catches the retracted conflation. Fix the gate.")
        failures += 1
    else:
        print(f"✓ selftest {g['name']}: correctly flagged (IoU {worst:.3f} < {min_iou})")

if failures:
    print(f"\n✗ {failures} spatial-provenance problem(s). A 'head-to-head' of non-co-located layers "
          f"compares different ground — the exact 2026-08-21 reach-provenance gap.")
    sys.exit(1)
print("\n✓ all declared comparisons are co-located; the known-bad pairing is still caught.")
PYEOF
