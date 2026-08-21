#!/usr/bin/env bash
# ── Spatial-provenance gate ──────────────────────────────────────────────────
# The first drift gate that reaches the PIXELS. Every existing gate enforces
# textual consistency; none could see that a "head-to-head" compared two different
# reaches, or that a reach named "arroyo" is geometrically a river, or that the
# imaged extent excludes the region a claim is about. Those are the 2026-08-21
# reach-provenance gap. See docs/2026-08-21-reach-provenance-gap.md.
#
# Reads .claude/spatial-provenance.json and enforces four things:
#   1. provenance   — every served web/public/maps/*.geojson is declared.
#   2. co-location  — layers shown head-to-head overlap (bbox IoU >= min_iou);
#                     SELF-TESTS by re-running the retracted Malpais pairing.
#   3. extent       — each reach's defined vs imaged extent reconciles, or is ack'd.
#   4. name↔geom    — a reach named for an ephemeral drainage but river-shaped is ack'd.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MANIFEST="$ROOT/.claude/spatial-provenance.json"
PY="$(command -v python3 || echo python3)"

exec "$PY" - "$MANIFEST" "$ROOT" <<'PYEOF'
import json, sys, os, glob, re

manifest_path, root = sys.argv[1], sys.argv[2]
if not os.path.exists(manifest_path):
    print(f"✗ spatial-provenance manifest missing: {manifest_path}"); sys.exit(1)
m = json.load(open(manifest_path))
min_iou = float(m.get("min_iou", 0.5))
reach_min_iou = float(m.get("reach_min_iou", 0.6))
reaches = m.get("reaches", {})
layers = m.get("layers", {})
failures = 0

def bbox(rel):
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return None, f"missing file: {rel}"
    gj = json.load(open(path))
    xs, ys = [], []
    def walk(a):
        if a and isinstance(a[0], (int, float)): xs.append(a[0]); ys.append(a[1])
        elif a:
            for x in a: walk(x)
    for f in gj.get("features", []):
        walk((f.get("geometry") or {}).get("coordinates"))
    if not xs: return None, f"no coordinates: {rel}"
    return (min(xs), min(ys), max(xs), max(ys)), None

def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0

def min_pair_iou(group):
    boxes, errs = {}, []
    for rel in group["layers"]:
        bb, err = bbox(rel)
        (errs.append(err) if err else boxes.__setitem__(rel, bb))
    if errs: return None, errs
    names = list(boxes); worst = 1.0; worst_pair = None
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            v = iou(boxes[names[i]], boxes[names[j]])
            if v < worst: worst, worst_pair = v, (names[i], names[j])
    return (worst, worst_pair), []

# ── Gate 1: provenance — every served layer declared, every declared layer exists
served = {os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "web/public/maps/*.geojson"))}
undeclared = sorted(served - set(layers))
for rel in undeclared:
    print(f"✗ [provenance] served layer not declared in the manifest: {rel}"); failures += 1
for rel in layers:
    if not os.path.exists(os.path.join(root, rel)):
        print(f"✗ [provenance] declared layer missing on disk: {rel}"); failures += 1
if not undeclared:
    print(f"✓ [provenance] all {len(served)} served map layers are declared")

# ── Gate 3: extent reconciliation — flag a TRUNCATION (imaged band offset to one
# side of the AOI, so part of the reach was never imaged, e.g. Malpais's northern
# arroyo), NOT a benign narrow-corridor artifact (a river centered in a tall AOI,
# e.g. Kirtland). Low bbox IoU alone over-flags narrow corridors; center-offset
# distinguishes them.
offset_threshold = float(m.get("offset_threshold", 0.10))
def center_offset(d, i):
    W, H = d[2]-d[0], d[3]-d[1]
    ox = ((i[0]+i[2])/2 - (d[0]+d[2])/2) / W if W else 0
    oy = ((i[1]+i[3])/2 - (d[1]+d[3])/2) / H if H else 0
    return max(abs(ox), abs(oy))
for rid, r in reaches.items():
    db, ib = r.get("defined_bbox"), r.get("imaged_bbox")
    if not (db and ib): continue
    v = iou(db, ib); off = center_offset(db, ib)
    if off > offset_threshold and not r.get("discrepancy_ack"):
        print(f"✗ [extent] reach '{rid}': imaged extent is TRUNCATED (center-offset {off:.2f} > "
              f"{offset_threshold}, IoU {v:.3f}) with no discrepancy_ack.")
        print(f"    part of the declared reach was not imaged/scored — acknowledge or reconcile it.")
        failures += 1
    elif off > offset_threshold:
        print(f"✓ [extent] reach '{rid}': truncated (offset {off:.2f}, IoU {v:.3f}) — acknowledged")
    else:
        print(f"✓ [extent] reach '{rid}': imaged band centered (offset {off:.2f}, IoU {v:.3f}) — corridor, not a gap")

# ── Gate 4: name ↔ geometry — an ephemeral-drainage name on river-shaped geometry
DRAINAGE = re.compile(r'\b(arroyo|wash|creek|draw|gulch)\b', re.I)
RIVERISH = re.compile(r'\b(river|mainstem|subwatershed|corridor)\b', re.I)
for rid, r in reaches.items():
    name, morph = r.get("name", ""), r.get("morphology", "")
    if DRAINAGE.search(name) and RIVERISH.search(morph) and not r.get("discrepancy_ack"):
        print(f"✗ [name↔geometry] reach '{rid}': name '{name}' implies an ephemeral drainage, "
              f"but morphology is '{morph}' — needs a discrepancy_ack.")
        failures += 1

# ── Gate 2: co-location of declared comparisons, + the self-test
for g in m.get("comparisons", []):
    res, errs = min_pair_iou(g)
    if errs:
        print(f"✗ [co-location] {g['name']}: {'; '.join(errs)}"); failures += 1; continue
    worst, pair = res
    if worst < min_iou:
        print(f"✗ [co-location] {g['name']} ({g.get('reach','')}) — NOT co-located "
              f"(worst pairwise IoU {worst:.3f} < {min_iou}):")
        print(f"      {os.path.basename(pair[0])} vs {os.path.basename(pair[1])}")
        print(f"    fix: compare layers on the SAME reach, or split into separate comparisons.")
        failures += 1
    else:
        print(f"✓ [co-location] {g['name']}: co-located (min pairwise IoU {worst:.3f})")

for g in m.get("selftest_expected_fail", []):
    res, errs = min_pair_iou(g)
    if errs:
        print(f"✓ [self-test] {g['name']}: not evaluable ({'; '.join(errs)}) — layers gone, ok"); continue
    worst, _ = res
    if worst >= min_iou:
        print(f"✗ SELF-TEST BROKEN: {g['name']} expected to FAIL but passed (IoU {worst:.3f}). Fix the gate.")
        failures += 1
    else:
        print(f"✓ [self-test] {g['name']}: correctly flagged (IoU {worst:.3f} < {min_iou})")

if failures:
    print(f"\n✗ {failures} spatial-provenance problem(s). A result whose data/labels/imagery/score/map "
          f"don't describe the same ground is the 2026-08-21 reach-provenance gap.")
    sys.exit(1)
print("\n✓ spatial provenance: layers declared, comparisons co-located, extents reconciled/ack'd, "
      "names consistent.")
PYEOF
