"""Render Excalidraw JSON to PNG (and a GitHub-ready SVG) using Playwright + headless Chromium.

For each input .excalidraw file, writes:
  - <name>.png — the screenshot, for embedding via Markdown <img> or direct viewing
  - <name>.svg — the same diagram as SVG markup, post-processed for GitHub rendering
                 (explicit width/height attrs + white background rect — see SKILL.md
                 "SVG Output for GitHub Embedding")

Usage:
    cd .claude/skills/excalidraw-diagram/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd .claude/skills/excalidraw-diagram/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_excalidraw(data: dict) -> list[str]:
    """Validate Excalidraw JSON structure. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if data.get("type") != "excalidraw":
        errors.append(f"Expected type 'excalidraw', got '{data.get('type')}'")

    if "elements" not in data:
        errors.append("Missing 'elements' array")
    elif not isinstance(data["elements"], list):
        errors.append("'elements' must be an array")
    elif len(data["elements"]) == 0:
        errors.append("'elements' array is empty — nothing to render")

    return errors


def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Compute bounding box (min_x, min_y, max_x, max_y) across all elements."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)

        # For arrows/lines, points array defines the shape relative to x,y
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    if min_x == float("inf"):
        return (0, 0, 800, 600)

    return (min_x, min_y, max_x, max_y)


def render(
    excalidraw_path: Path,
    output_path: Path | None = None,
    scale: int = 2,
    max_width: int = 1920,
) -> Path:
    """Render an .excalidraw file to PNG. Returns the output PNG path."""
    # Import playwright here so validation errors show before import errors
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.", file=sys.stderr)
        print("Run: cd .claude/skills/excalidraw-diagram/references && uv sync && uv run playwright install chromium", file=sys.stderr)
        sys.exit(1)

    # Read and validate
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {excalidraw_path}: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_excalidraw(data)
    if errors:
        print(f"ERROR: Invalid Excalidraw file:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Compute viewport size from element bounding box
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80
    diagram_w = max_x - min_x + padding * 2
    diagram_h = max_y - min_y + padding * 2

    # Cap viewport width, let height be natural
    vp_width = min(int(diagram_w), max_width)
    vp_height = max(int(diagram_h), 600)

    # Output path
    if output_path is None:
        output_path = excalidraw_path.with_suffix(".png")

    # Template path (same directory as this script)
    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    template_url = template_path.as_uri()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
                print("ERROR: Chromium not installed for Playwright.", file=sys.stderr)
                print("Run: cd .claude/skills/excalidraw-diagram/references && uv run playwright install chromium", file=sys.stderr)
                sys.exit(1)
            raise

        page = browser.new_page(
            viewport={"width": vp_width, "height": vp_height},
            device_scale_factor=scale,
        )

        # Capture console and network failures — when the esm.sh bundle fails
        # to load, the surfaced error is a generic Timeout. The actual cause
        # (CORS, 404, syntax error, etc.) shows up in the page console; route
        # it to stderr so the script's output explains what went wrong.
        page.on("console", lambda msg: print(f"  [page console.{msg.type}] {msg.text}", file=sys.stderr))
        page.on("pageerror", lambda exc: print(f"  [page error] {exc}", file=sys.stderr))
        page.on("requestfailed", lambda req: print(f"  [request failed] {req.url} — {req.failure}", file=sys.stderr))

        # Load the template
        page.goto(template_url)

        # Wait for the ES module to load (imports from esm.sh). The
        # `@excalidraw/excalidraw?bundle` URL serves a small entry shim but
        # the browser pulls in many transitive modules afterwards; 30s was
        # too tight on slower networks. 90s is a comfortable ceiling — if we
        # ever hit that, the CDN is genuinely down rather than slow.
        page.wait_for_function("window.__moduleReady === true", timeout=90000)

        # Inject the diagram data and render
        json_str = json.dumps(data)
        result = page.evaluate(f"window.renderDiagram({json_str})")

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
            print(f"ERROR: Render failed: {error_msg}", file=sys.stderr)
            browser.close()
            sys.exit(1)

        # Wait for render completion signal
        page.wait_for_function("window.__renderComplete === true", timeout=15000)

        # Screenshot the SVG element to PNG
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            print("ERROR: No SVG element found after render.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        svg_el.screenshot(path=str(output_path))

        # Also save the SVG markup as a sibling file. GitHub renders SVG inline in
        # markdown views (PNG must be embedded with <img>; SVG can also be linked).
        # Post-process to add the GitHub-friendly attributes documented in
        # SKILL.md "SVG Output for GitHub Embedding":
        #   1. explicit width + height (so GitHub doesn't downscale text below readable)
        #   2. white background rect (so text is readable on dark theme)
        svg_markup = page.evaluate("document.querySelector('#root svg').outerHTML")
        if not svg_markup or not svg_markup.strip():
            # Earlier `query_selector` already proved the SVG element exists, so
            # an empty outerHTML here would be unexpected — warn loudly but don't
            # fail the run (PNG was still written above).
            print("WARNING: outerHTML was empty; .svg sibling not written", file=sys.stderr)
        else:
            svg_output_path = output_path.with_suffix(".svg")
            svg_markup = _make_github_friendly(svg_markup)
            svg_output_path.write_text(svg_markup, encoding="utf-8")

        browser.close()

    return output_path


def _make_github_friendly(svg_markup: str) -> str:
    """Post-process Excalidraw's exportToSvg output so it renders well on GitHub.

    Two adjustments (see SKILL.md "SVG Output for GitHub Embedding"):
      1. Ensure the root <svg> has explicit width/height attributes matching the
         viewBox — without them, GitHub downscales to fit the markdown column and
         text becomes illegible.
      2. Insert a white <rect> as the first child of <svg> so text colored for a
         light background stays readable on GitHub's dark theme.
    """
    import re

    # Parse the root <svg> tag attributes.
    match = re.match(r"<svg([^>]*)>", svg_markup)
    if not match:
        return svg_markup  # malformed; leave alone
    attrs = match.group(1)

    # Extract viewBox dimensions. Excalidraw always emits a viewBox.
    vb_match = re.search(r'viewBox="\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)"', attrs)
    if vb_match:
        _, _, vb_w, vb_h = vb_match.groups()
        # Add width/height if missing.
        if 'width=' not in attrs:
            attrs += f' width="{vb_w}"'
        if 'height=' not in attrs:
            attrs += f' height="{vb_h}"'
        # Build the white bg rect using viewBox dimensions.
        bg_rect = f'<rect width="{vb_w}" height="{vb_h}" fill="#ffffff"/>'
    else:
        bg_rect = '<rect width="100%" height="100%" fill="#ffffff"/>'

    # Reconstruct: open tag with merged attrs, then inject bg rect as first child.
    new_open = f"<svg{attrs}>{bg_rect}"
    return svg_markup.replace(match.group(0), new_open, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Excalidraw JSON to PNG")
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output PNG path (default: same name with .png)")
    parser.add_argument("--scale", "-s", type=int, default=2, help="Device scale factor (default: 2)")
    parser.add_argument("--width", "-w", type=int, default=1920, help="Max viewport width (default: 1920)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    png_path = render(args.input, args.output, args.scale, args.width)
    svg_path = png_path.with_suffix(".svg")
    print(str(png_path))
    if svg_path.exists():
        print(str(svg_path))


if __name__ == "__main__":
    main()
