"""Phase 3A — the cross-sensor gate: measure RF's Sentinel-2 → Landsat sensor penalty.

The Phase-3 deep-time product needs a model fit on modern Sentinel-2 (2015→) to hold on
Landsat (1984→), the only sensor reaching the pre-beetle era. Before committing to any
archive architecture, 3A measures — on ground truth, at a single date — how much accuracy is
lost purely to the sensor change. See ``docs/specs/2026-07-18-phase3-deeptime-change.md`` and
the write-up ``docs/2026-07-18-phase3a-cross-sensor-result.md``.

Method (the same-pixel comparison that isolates the sensor):
  1. Fetch **S2 2020** and **Landsat-8 2020** for one reach on **one enforced 10 m grid**,
     the **6 shared bands** (blue/green/red/NIR/SWIR-1/SWIR-2), **12 monthly composites**,
     each converted from its own DN scaling to **surface reflectance (0-1)** so the values
     are comparable. Landsat's native 30 m is resampled to the 10 m grid — this aligns the
     grids without inventing detail, so the resolution disadvantage is preserved, not hidden.
  2. Rasterise NMRipMap riparian labels onto that grid (via the tested ``label_layer`` +
     ``validate_reach`` path — never a raw fetch).
  3. Train RF on the **S2** side; score the **same spatially-held-out pixels** twice — on their
     S2 features (in-sensor) and their Landsat features (cross-sensor). The AUC drop IS the
     sensor penalty, isolated because the pixels and labels are identical.

A transient STAC search failure must never masquerade as a no-data month: the fetch flags
``SEARCH-FAILED`` months explicitly rather than silently writing NaN (method receipt).

Usage:
    PYTHONPATH=python-etl python olmoearth_run_data/riparian_extent/phase3a_cross_sensor.py \\
        --gdb .tmp/nmripmap_gdb/.../GRSJ_Version2_0Plus_North.gdb --dest .tmp/xsensor.npz
    # add --score-only to re-score a cached cube without re-fetching.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from rasterio.transform import Affine, from_bounds
from rasterio.warp import Resampling, reproject
from pyproj import Transformer
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from riparian.labels import label_layer, validate_layer  # noqa: E402
from validate_reach import gdb_reader_factory, rasterize_labels  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("phase3a")

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
FARMINGTON_XSENSOR_BBOX = (-108.33, 36.70, -108.19, 36.79)  # covers the Farmington label windows
UTM = "EPSG:32612"  # San Juan Basin (108 W) is UTM 12N
MONTHS = [(f"2020-{m:02d}-01", f"2020-{m:02d}-28") for m in range(1, 13)]
S2_BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]
LS_BANDS = ["blue", "green", "red", "nir08", "swir16", "swir22"]
S2_SCALE, S2_OFF = 1 / 10000.0, 0.0
LS_SCALE, LS_OFF = 0.0000275, -0.2  # Landsat C2-L2 surface-reflectance DN → reflectance
BLOCK = 64  # spatial checkerboard block size (px) for the leak-resistant train/test split


def _grid(bbox: tuple[float, float, float, float]) -> tuple[Affine, int, int]:
    """The single 10 m UTM grid both sensors are resampled onto."""
    tr = Transformer.from_crs("EPSG:4326", UTM, always_xy=True)
    minx, miny = tr.transform(bbox[0], bbox[1])
    maxx, maxy = tr.transform(bbox[2], bbox[3])
    minx, miny, maxx, maxy = int(minx), int(miny), int(maxx), int(maxy)
    w, h = (maxx - minx) // 10, (maxy - miny) // 10
    return from_bounds(minx, miny, maxx, maxy, w, h), h, w


def _read_band(href: str, scale: float, off: float, affine: Affine, h: int, w: int) -> np.ndarray:
    """Reproject one COG band onto the common grid, as reflectance; NaN where out of range."""
    for attempt in range(3):
        dst = np.full((h, w), np.nan, np.float32)  # fresh buffer per attempt — a retry must not keep partial data
        try:
            with rasterio.open(href) as src:
                reproject(rasterio.band(src, 1), dst, src_transform=src.transform, src_crs=src.crs,
                          dst_transform=affine, dst_crs=UTM, resampling=Resampling.bilinear)
            r = dst * scale + off
            r[(r < 0) | (r > 1.2)] = np.nan
            return r
        except Exception as ex:  # noqa: BLE001 — a COG read is best-effort; retry then give up
            if attempt == 2:
                logger.warning("    band read failed: %s", str(ex)[:50])
    return np.full((h, w), np.nan, np.float32)


def _fetch(coll: str, bands: list[str], scale: float, off: float, bbox, affine, h, w,
           platform: str | None = None) -> tuple[np.ndarray, list[int]]:
    """12-month cube for one sensor. Distinguishes genuine-empty from transient search failure."""
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    cube, failed = [], []
    for i, (s, e) in enumerate(MONTHS):
        q: dict = {"eo:cloud_cover": {"lt": 40}}
        if platform:
            q["platform"] = {"eq": platform}
        items = None  # None = search never succeeded; [] = ran, genuinely no scenes
        for attempt in range(6):
            try:
                items = list(cat.search(collections=[coll], bbox=list(bbox),
                                        datetime=f"{s}/{e}", query=q).items())
                break
            except Exception as ex:  # noqa: BLE001
                if attempt == 5:
                    logger.warning("  %s m%d: SEARCH FAILED: %s", coll[:8], i + 1, str(ex)[:50])
                else:
                    time.sleep(2 + 2 * attempt)
        if items is None:  # transient — NOT no-data; flag it, never poison silently
            failed.append(i + 1)
            cube.append(np.full((6, h, w), np.nan, np.float32))
            continue
        if not items:
            cube.append(np.full((6, h, w), np.nan, np.float32))
            logger.info("  %s m%d: no scenes (genuine)", coll[:8], i + 1)
            continue
        it = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100))[0]
        cube.append(np.stack([_read_band(it.assets[b].href, scale, off, affine, h, w) for b in bands]))
        logger.info("  %s m%d: %s", coll[:8], i + 1, it.id[:22])
    logger.info("  == %s: %d/12 populated | search-failed=%s", coll[:8], 12 - len(failed), failed)
    return np.concatenate(cube, 0), failed


def fetch_cubes(bbox, dest: Path) -> None:
    """Materialise both sensor cubes to ``dest`` (.npz). Raises if any month failed transiently."""
    affine, h, w = _grid(bbox)
    logger.info("grid %dx%d @10m %s", h, w, UTM)
    s2, s2_fail = _fetch("sentinel-2-l2a", S2_BANDS, S2_SCALE, S2_OFF, bbox, affine, h, w)
    ls, ls_fail = _fetch("landsat-c2-l2", LS_BANDS, LS_SCALE, LS_OFF, bbox, affine, h, w,
                         platform="landsat-8")
    if s2_fail or ls_fail:
        # Refuse to write a poisoned cache: a NaN-from-timeout month must not be reused by --score-only.
        raise RuntimeError(f"transient search failures — rerun: s2={s2_fail} ls={ls_fail}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez(dest, s2=s2, ls=ls, affine=np.array(affine).reshape(-1)[:6], h=h, w=w)
    logger.info("saved %s (clean: every month populated or genuinely empty)", dest)


def _impute(train_x: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Fill NaN with per-column median from TRAIN rows only (RF cannot take NaN)."""
    med = np.nanmedian(train_x, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    return np.where(np.isfinite(x), x, med)


def score(bbox, dest: Path, gdb: str) -> float:
    """Train RF on S2, score the same held-out pixels on S2 and Landsat; return the penalty."""
    d = np.load(dest)
    s2, ls = d["s2"], d["ls"]
    h, w = int(d["h"]), int(d["w"])
    affine = Affine(*d["affine"])
    fc, stats = label_layer.build_extent_labels(bbox, corridor=None, reader=gdb_reader_factory(gdb))
    mask = rasterize_labels(fc, affine, UTM, (h, w))
    logger.info("labels: %d riparian + %d corridor-neg polygons", stats.n_positive, stats.n_negative)

    pos_cls = validate_layer.POSITIVE_CLASS
    neg_cls = validate_layer.CORRIDOR_NEGATIVE_CLASSES
    s2f, lsf, m = s2.reshape(72, -1).T, ls.reshape(72, -1).T, mask.reshape(-1)
    rows, cols = np.divmod(np.arange(h * w), w)
    keep = np.isin(m, (pos_cls,) + tuple(neg_cls)) & np.isfinite(s2f).any(1) & np.isfinite(lsf).any(1)
    y = (m[keep] == pos_cls).astype(int)
    s2f, lsf, rr, cc = s2f[keep], lsf[keep], rows[keep], cols[keep]
    logger.info("usable pixels: %d (%d riparian / %d corridor-neg)", keep.sum(), y.sum(), (y == 0).sum())

    tr = (rr // BLOCK + cc // BLOCK) % 2 == 0  # spatial checkerboard: train/test share no pixel
    te = ~tr
    if y[tr].sum() < 20 or y[te].sum() < 20:
        raise RuntimeError("too few positives on one side of the spatial split")

    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                min_samples_leaf=1, max_features="sqrt", n_jobs=-1, random_state=0)
    rf.fit(_impute(s2f[tr], s2f[tr]), y[tr])

    def auc(x: np.ndarray) -> float:
        p = rf.predict_proba(x)[:, 1]
        return validate_layer.auc(p[y[te] == 1], p[y[te] == 0])

    in_sensor = auc(_impute(s2f[tr], s2f[te]))
    cross = auc(_impute(lsf[tr], lsf[te]))
    logger.info("")
    logger.info("═══ Phase 3A — RF cross-sensor penalty ═══")
    logger.info("  in-sensor  (train S2 → test S2)        AUC = %.3f", in_sensor)
    logger.info("  cross-sensor (train S2 → test Landsat)  AUC = %.3f", cross)
    logger.info("  SENSOR PENALTY = %+.3f", in_sensor - cross)
    return in_sensor - cross


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gdb", required=True, help="local NMRipMap File Geodatabase")
    ap.add_argument("--dest", type=Path, default=HERE / ".tmp/xsensor.npz", help="cube cache (.npz)")
    ap.add_argument("--score-only", action="store_true", help="skip fetch; re-score a cached cube")
    a = ap.parse_args()
    bbox = FARMINGTON_XSENSOR_BBOX
    if not a.score_only:
        os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "4")
        os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
        fetch_cubes(bbox, a.dest)
    score(bbox, a.dest, a.gdb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
