#!/usr/bin/env bash
# Render the encoding-loop hero infographic from HTML source to PNG via
# headless Chromium (Playwright). Edit docs/encoding-loop-hero.html with
# any text/CSS tweak, then run this script — re-render takes ~3 seconds
# and is fully deterministic (same source → identical PNG byte-for-byte).
#
# This is the human-readable counterpart to the .excalidraw → .svg + .png
# pipeline in rebuild-diagrams.sh. Both render artifacts that ship in the
# repo from a source-of-truth file you can edit directly.
#
# Usage:
#   .claude/scripts/render-hero.sh                    # render docs/encoding-loop-hero.html
#   .claude/scripts/render-hero.sh path/to/file.html  # render any HTML file
#
# Requires: uv (https://docs.astral.sh/uv/) — manages Playwright + Chromium.

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SRC="${1:-$REPO_ROOT/docs/encoding-loop-hero.html}"
OUT="${SRC%.html}.png"

if [ ! -f "$SRC" ]; then
  echo "ERROR: source HTML not found: $SRC" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' not found. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

# Render at 1024×1536 with 2× device pixel ratio (retina-sharp output).
# device_scale_factor=2 yields a 2048×3072 raster while the layout is laid
# out for a 1024×1536 viewport — this is what gives crisp text on social
# previews and downstream embeds.
uv run --with playwright python - <<PYEOF
from playwright.sync_api import sync_playwright
import os, sys

src = "file://${SRC}"
out = "${OUT}"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1024, "height": 1536}, device_scale_factor=2)
    page.goto(src, wait_until="networkidle")
    page.wait_for_timeout(1500)  # let Google Fonts resolve
    page.screenshot(path=out, full_page=False, clip={"x": 0, "y": 0, "width": 1024, "height": 1536})
    browser.close()

size_kb = os.path.getsize(out) / 1024
print(f"Rendered: {out} ({size_kb:.0f} KB)")
PYEOF
