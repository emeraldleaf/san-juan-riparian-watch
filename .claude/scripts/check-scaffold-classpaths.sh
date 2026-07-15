#!/usr/bin/env bash
#
# Every `class_path:` in the OlmoEarth scaffold must actually import.
#
# WHY THIS EXISTS. The scaffold shipped with FIVE class paths that did not exist —
# `olmoearth_run.partitioners.grid.GridPartitioner` and friends. Every class NAME was right and
# every MODULE path was wrong (the real one is `olmoearth_run.runner.tools.partitioners.
# grid_partitioner`). They were written from a plausible memory of the package layout, never
# imported, and nothing in the repo could tell:
#
#   - the drift gates check doc/config SHAPE, not whether a symbol resolves;
#   - CodeRabbit reviews the diff, and a wrong-but-plausible dotted path reads fine;
#   - the Phase-0 spec listed "confirm GridPartitioner imports" as a step for a HUMAN to run.
#
# A step a human must remember to run is not a gate. This one is now mechanical.
#
# The cost of NOT having it: these paths blow up at `olmoearth_run` startup — which, per the plan,
# is Phase 1, on a rented GPU. A $0 typo would have been discovered on a paid clock.
#
# Usage: check-scaffold-classpaths.sh [venv-python]
set -uo pipefail

PY="${1:-.venv-olmoearth/bin/python}"
SCAFFOLD="olmoearth_run_data"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

if [[ ! -x "$PY" ]]; then
    echo -e "${YELLOW}!${NC} $PY not found — skipping class-path check (venv not built)"
    exit 0
fi

# macOS ships bash 3.2 — no `mapfile`. Keep this portable; a gate that only runs on the author's
# machine is not a gate.
PATHS=$(grep -rhoE 'class_path:[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*' "$SCAFFOLD" \
    | sed -E 's/class_path:[[:space:]]*//' | sort -u)

if [[ -z "$PATHS" ]]; then
    echo -e "${RED}✗${NC} no class_path entries found under $SCAFFOLD/ — is the scaffold there?"
    exit 1
fi

fail=0
count=0
for cp in $PATHS; do
    count=$((count + 1))
    # rslearn/torch class paths live in other packages; import whatever is declared, wherever it lives.
    # Capture stderr so a failure shows the ACTUAL error (ModuleNotFoundError, wrong attr, ...).
    # For a gate whose whole job is to catch $0 typos before a paid GPU clock, "does not import"
    # with no detail just forces a manual re-run to see what everyone already paid to avoid.
    if err=$("$PY" - "$cp" <<'PY' 2>&1
import importlib, sys
cp = sys.argv[1]
module, _, cls = cp.rpartition(".")
obj = getattr(importlib.import_module(module), cls)
PY
    ); then
        echo -e "  ${GREEN}✓${NC} $cp"
    else
        echo -e "  ${RED}✗${NC} $cp — does not import"
        echo "      ${err##*$'\n'}"
        fail=1
    fi
done

if [[ $fail -ne 0 ]]; then
    echo -e "\n${RED}✗ scaffold has class paths that do not resolve.${NC}"
    echo "  These fail at runner startup — which is Phase 1, on a GPU you are paying for."
    exit 1
fi

echo -e "${GREEN}✓${NC} all ${count} scaffold class paths import"
