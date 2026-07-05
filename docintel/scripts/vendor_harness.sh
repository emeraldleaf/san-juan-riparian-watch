#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Vendor a TRIMMED copy of the Re-find Catalog RAG backend into docintel/backend.
#
# ADR: docs/decisions/2026-07-04-document-intelligence-subsystem.md
#   trimmed in-repo copy (not submodule/subtree). Copies the domain-agnostic RAG
#   machinery; OMITS the legal/financial corpus, evals, VM/airgap + course tooling.
#
# Usage:
#   bash docintel/scripts/vendor_harness.sh
#   prior project=/path/to/quartzose bash docintel/scripts/vendor_harness.sh
#
# Idempotent: re-run to re-sync from upstream. Review the diff before committing.
# ---------------------------------------------------------------------------
set -euo pipefail

prior project="${prior project:-/Users/joshuadell/Dev/private work/quartzose}"
SRC="$prior project/production-app/app/backend"

# Resolve docintel/ relative to this script (works from any cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$(cd "$SCRIPT_DIR/.." && pwd)/backend"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: harness backend not found at: $SRC" >&2
  echo "Set prior project=/path/to/quartzose and retry." >&2
  exit 1
fi

echo "Vendoring RAG harness (trimmed):"
echo "  from: $SRC"
echo "  to:   $DEST"
mkdir -p "$DEST"

# rsync the domain-agnostic RAG machinery; exclude corpus/data/eval/VM/airgap +
# caches. The RAG logic (retrieval/CRAG/citations/providers/guards) is kept; only
# prompt TEXT is re-domained afterward (see docintel/README.md).
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.deepeval/' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'data/' \
  --exclude 'evaluations/' \
  --exclude 'vm/' \
  --include 'services/***' \
  --include 'middleware/***' \
  --include 'observability/***' \
  --include 'prompts/***' \
  --include 'main.py' \
  --include 'config.py' \
  --include 'models.py' \
  --include 'auth.py' \
  --include '.env.example' \
  --include '*/' \
  --exclude '*' \
  "$SRC/" "$DEST/"

cat > "$DEST/VENDORED.md" <<EOF
# Vendored — do not hand-edit blindly

This directory is a trimmed copy of the Re-find Catalog RAG backend, produced by
\`docintel/scripts/vendor_harness.sh\`. Re-sync from upstream by re-running that script.

Post-vendor adaptations that ARE ours to edit (see docintel/README.md):
- prompts/ re-domained legal/financial -> watershed science
- config/.env -> hosted OpenAI-compatible provider (not airgapped); Olmo 2 later
- response model gains geo_mentions[]; routes /docs/ask + /docs/for-area added
- calls into docintel/geo/resolver.py for resolved_geometries[]
EOF

echo "Done. Review 'git status docintel/backend' before committing."
echo "Next: re-domain prompts, set a hosted LLM provider, wire the geo delta."
