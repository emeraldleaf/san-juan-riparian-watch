"""Generate NAIP-2020 overlay chips for the Phase-0 eye-check (issue #46).

The shift test found a marginal ~1 px (10 m) label-vs-imagery offset on Farmington (pooled AUC 0.765
at (1,0) vs 0.752 unshifted, +0.013). It is either real sub-pixel registration slack (0.6 m
NAIP-drawn NMRipMap polygons rasterised onto a 10 m S2 grid) or noise — and only the eyes settle it.
NAIP 2020 is the *exact* imagery NMRipMap was photo-interpreted from, so it is the ground truth, not
a proxy.

This renders, per selected window, three side-by-side panels:
  1. NAIP alone.
  2. NAIP + riparian label boundary (cyan) at its true position.
  3. NAIP + the same boundary shifted 10 m SOUTH — the correction the shift test prefers (see SHIFT_M).

If panel 2's cyan line sits ON the green riparian vegetation and panel 3 (the shifted one) sits OFF
it → labels are aligned, accept. If panel 3 fits BETTER → a real offset; shift labels before Phase 1.

    PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/naip_overlay.py [n_windows]
"""

from __future__ import annotations

import json
import signal
import socket
import sys
import time
from pathlib import Path

socket.setdefaulttimeout(60)  # bound the STAC search HTTP reads


class _FetchTimeout(Exception):
    """A single NAIP fetch attempt blew its deadline (GDAL/CURL can hang on a stalled PC gateway)."""


def _raise_timeout(signum, frame):  # SIGALRM handler signature
    raise _FetchTimeout

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon as MplPolygon
import planetary_computer
import pystac_client
import rasterio
import shapely.geometry
import shapely.ops
from rasterio.warp import transform_bounds
from shapely.affinity import translate

HERE = Path(__file__).parent
DATASET = HERE / "dataset"
OUT = HERE / "naip_chips"
RES_M = 10.0
# The shift test's best offset is (dy=+1, dx=0). In a north-up array dy=+1 moves the label mask DOWN
# one row = 10 m SOUTH, and that *improves* the NDVI fit — i.e. the vegetation sits ~1 px south of the
# labels. So the shift-test-preferred correction is to move the labels south: yoff = -10 m in UTM
# (northing decreases southward). Panel 3 shows that direction — the one that, if the offset is real,
# should fit BETTER than panel 2.
SHIFT_M = -10.0
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def _window_utm_bounds(meta: dict) -> tuple[float, float, float, float, str]:
    """Window bounds (pixel indices) → UTM metres (minx, miny, maxx, maxy), + CRS."""
    px = meta["bounds"]  # [col0, row0, col1, row1]
    crs = meta["projection"]["crs"]
    xr = meta["projection"]["x_resolution"]
    yr = meta["projection"]["y_resolution"]  # negative
    xs = sorted([px[0] * xr, px[2] * xr])
    ys = sorted([px[1] * yr, px[3] * yr])
    return xs[0], ys[0], xs[1], ys[1], crs


def _riparian_polys_utm(window: Path, meta: dict) -> list[tuple[shapely.geometry.base.BaseGeometry, str]]:
    """Riparian (class 1) label polygons, in UTM metres, tagged 'woody' or 'herb'.

    The distinction matters for the eye-check: **woody** riparian (native + introduced trees/shrubs)
    shows as green canopy on NAIP and is what an alignment offset would be visible against.
    **Herbaceous** riparian (floodplain grass/sedge) shows as *tan grassland*, not green — so a
    herbaceous polygon over pale ground is correct, not a misplacement. Hatching it keeps that from
    reading as an error.
    """
    fc = json.loads((window / "layers/label/data.geojson").read_text())
    xr = meta["projection"]["x_resolution"]
    yr = meta["projection"]["y_resolution"]
    out = []
    for feat in fc["features"]:
        props = feat.get("properties") or {}
        if int(props.get("class", 0) or 0) != 1:
            continue
        kind = "herb" if "herbaceous" in (props.get("label") or "") else "woody"
        geom = shapely.geometry.shape(feat["geometry"])  # in the window's pixel grid
        # pixel grid → UTM metres: the data.geojson coords are pixel indices in the window projection.
        out.append((shapely.ops.transform(lambda x, y, z=None: (x * xr, y * yr), geom), kind))
    return out


def _fetch_naip(minx: float, miny: float, maxx: float, maxy: float, utm_crs: str) -> tuple[np.ndarray, tuple]:
    """Fetch a NAIP-2020 RGB crop for the UTM bbox. Returns (H,W,3) uint8 and the UTM extent.

    Planetary Computer's blob gateway throws intermittent OriginTimeouts, so retry a few times and
    re-sign each attempt (signed URLs expire) before giving up on a window.
    """
    lon0, lat0, lon1, lat1 = transform_bounds(utm_crs, "EPSG:4326", minx, miny, maxx, maxy)
    last: Exception | None = None
    env = rasterio.Env(GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_TIMEOUT="45")
    signal.signal(signal.SIGALRM, _raise_timeout)
    for attempt in range(8):
        try:
            signal.alarm(75)  # hard per-attempt deadline — GDAL_HTTP_TIMEOUT does not always fire
            cat = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
            items = list(cat.search(collections=["naip"], bbox=[lon0, lat0, lon1, lat1],
                                    datetime="2020-01-01/2020-12-31").items())
            if not items:
                raise RuntimeError("no NAIP 2020 tile over this window")
            href = items[0].assets["image"].href
            with env, rasterio.open(href) as src:
                win = rasterio.windows.from_bounds(minx, miny, maxx, maxy, transform=src.transform)
                rgb = src.read([1, 2, 3], window=win).transpose(1, 2, 0)
            signal.alarm(0)
            return rgb, (minx, miny, maxx, maxy)
        except Exception as e:  # retry gateway timeouts, hangs (_FetchTimeout), url expiry
            signal.alarm(0)  # cancel FIRST — else the 75s deadline could fire during the sleep below
            last = e
            time.sleep(5 * (attempt + 1))  # PC blob gateway blips clear within minutes
    raise RuntimeError(f"NAIP fetch failed after retries: {str(last)[:80]}")


def _panel(ax, rgb, extent, polys, title, shift_m=0.0):
    ax.imshow(rgb, extent=[extent[0], extent[2], extent[1], extent[3]])
    for g, kind in polys:
        gg = translate(g, yoff=shift_m) if shift_m else g
        for geom in (gg.geoms if hasattr(gg, "geoms") else [gg]):
            xy = np.asarray(geom.exterior.coords)
            if kind == "woody":  # green canopy — the alignment target: solid cyan outline
                ax.plot(xy[:, 0], xy[:, 1], color="cyan", linewidth=1.5)
            else:  # herbaceous (grass/sedge) — hatched so tan-over-grassland doesn't read as an error
                ax.add_patch(MplPolygon(xy, closed=True, facecolor="none", edgecolor="gold",
                                        hatch="///", linewidth=0.8, alpha=0.9))
    # Clip to the NAIP extent so a shifted polygon can't expand the axes (stray edge lines / white bands).
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.set_title(title, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    OUT.mkdir(exist_ok=True)
    windows = sorted((DATASET / "windows/train").glob("*/"))
    # pick windows with the most riparian label area — the ones where an offset would show
    scored = []
    for w in windows:
        meta = json.loads((w / "metadata.json").read_text())
        try:
            polys = _riparian_polys_utm(w, meta)
        except FileNotFoundError:
            continue
        # rank by WOODY area — those are the green-canopy boundaries the eye-check is about
        woody_area = sum(g.area for g, kind in polys if kind == "woody")
        if woody_area > 0:
            scored.append((woody_area, w, meta, polys))
    scored.sort(reverse=True, key=lambda t: t[0])
    picked = scored[:n]
    print(f"rendering {len(picked)} riparian-heavy windows of {len(scored)} labelled")

    for i, (area, w, meta, polys) in enumerate(picked, 1):
        minx, miny, maxx, maxy, crs = _window_utm_bounds(meta)
        try:
            rgb, extent = _fetch_naip(minx, miny, maxx, maxy, crs)
        except Exception as e:  # a chip that won't fetch just gets skipped
            print(f"  [{i}] {w.name}: SKIP ({e})")
            continue
        fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
        _panel(axes[0], rgb, extent, [], "1. NAIP 2020 (bare)")
        _panel(axes[1], rgb, extent, polys, "2. label boundary — TRUE position")
        _panel(axes[2], rgb, extent, polys, "3. label shifted +1px S (shift-test's preferred fix)",
               shift_m=SHIFT_M)
        fig.suptitle(
            f"{w.name} — does CYAN (woody) sit on the green?  panel 2 (as-is) vs 3 (10 m S)\n"
            "cyan line = woody riparian (green canopy — judge this)   ·   "
            "gold hatch = herbaceous (grass/sedge — tan on NAIP, not an error)",
            fontsize=9,
        )
        fig.tight_layout()
        dest = OUT / f"chip_{i:02d}_{w.name}.png"
        fig.savefig(dest, dpi=130, bbox_inches="tight")
        plt.close(fig)
        print(f"  [{i}] {dest.name}")
    print(f"\nchips in {OUT}/  — open them and compare panel 2 (as-is) vs panel 3 (10 m S).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
