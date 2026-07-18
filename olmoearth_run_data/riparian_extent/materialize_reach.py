"""Materialize a phenologically-aligned Sentinel-2 time-series cube for any reach.

The reusable form of the one-off Malpais build. Given a reach (or an arbitrary
bounding box) and a label source, it produces an rslearn dataset of per-window
Sentinel-2 GeoTIFFs — **12 monthly median mosaics over 366 days** — that is
directly comparable, pixel-for-pixel and month-for-month, to every other reach
built the same way. That cross-reach comparability is the whole point: a
transfer experiment is only valid if the features were composited identically
(see ``docs/2026-07-18-reach-cube-materialization.md`` for the why).

Pipeline (also drawn in ``docs/malpais-download-pipeline.svg``):

    label source ──▶ build_extent_labels() ──▶ rslearn_dataset.build()
                                                     │ 32×32 windows, riparian-only
                                                     ▼
    rslearn dataset prepare → ingest → materialize   (STAC + COG range-reads, --workers N)
                                                     ▼
                                verify_materialized() ──▶ dataset/windows/*.tif

The label source is a swappable ``LabeledPolygonReader`` Protocol:
* ``--gdb <path>`` — a local NMRipMap File Geodatabase (offline, bypasses the
  flaky live ArcGIS backend), routed through the same ``nmripmap._to_labeled``
  crosswalk so it is not a raw fetch.
* omit ``--gdb`` — the live ArcGIS ``nmripmap.fetch_labeled`` path.

Coverage: NMRipMap is **New Mexico only**. For Colorado/Utah reaches, supply a
different reader (CO-RIP, CSU points) — the Protocol is the seam for that.

Usage:
    # a named reach from a local GDB
    python materialize_reach.py --reach malpais --gdb path/to/NMRipMap.gdb \\
        --dest dataset_malpais --workers 8

    # an arbitrary AOI (minlon minlat maxlon maxlat, EPSG:4326)
    python materialize_reach.py --bbox -108.82 36.81 -108.67 36.95 \\
        --gdb path/to/NMRipMap.gdb --dest dataset_myreach

    # build the labelled windows only, skip the (slow) S2 download — for a smoke test
    python materialize_reach.py --reach malpais --gdb ... --dest /tmp/d --skip-download
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The riparian package lives in python-etl/; validate_reach.py sits beside this file.
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))
sys.path.insert(0, str(HERE))

logger = logging.getLogger("materialize_reach")

# Named reaches, reused from validate_reach so the two tools cannot drift apart.
from validate_reach import FARMINGTON_BBOX, MALPAIS_BBOX, gdb_reader_factory  # noqa: E402

REACHES: dict[str, tuple[float, float, float, float]] = {
    "farmington": FARMINGTON_BBOX,
    "malpais": MALPAIS_BBOX,
}
SCAFFOLD_CONFIG = HERE / "dataset.json"


def _redirect_temp(dest: Path) -> None:
    """Keep rslearn/GDAL scratch off the boot disk — the Phase-0 disk-fill trap.

    ``ingest`` stages whole S2 granules through ``TMPDIR``; ``materialize`` uses
    GDAL's own ``CPL_TMPDIR``. Both default to the boot volume and will fill it.
    We point them at a ``.tmp`` beside the dataset (same drive as the output) and
    cap the GDAL block cache. Setting only one is a trap — set all of them.
    """
    tmp = dest.parent / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for var in ("TMPDIR", "TMP", "TEMP", "CPL_TMPDIR"):
        os.environ[var] = str(tmp)
    os.environ.setdefault("GDAL_CACHEMAX", "256")
    logger.info("temp redirected to %s (TMPDIR + CPL_TMPDIR); GDAL_CACHEMAX=256", tmp)


def _rslearn(step: str, dest: Path, workers: int) -> None:
    """Run one rslearn dataset CLI step, streaming its output."""
    cmd = [sys.executable, "-m", "rslearn.main", "dataset", step,
           "--root", str(dest), "--workers", str(workers)]
    logger.info("rslearn dataset %s (--workers %d) ...", step, workers)
    subprocess.run(cmd, check=True)


def materialize_reach(
    dest: Path,
    bbox: tuple[float, float, float, float],
    reader,
    workers: int = 8,
    skip_download: bool = False,
) -> int:
    """Build labelled windows for ``bbox`` and materialize the S2 cube into ``dest``.

    Args:
        dest: Dataset root to create (rebuilt if it exists).
        bbox: AOI ``(minlon, minlat, maxlon, maxlat)`` in EPSG:4326.
        reader: A ``LabeledPolygonReader`` — the label source.
        workers: Concurrency for the I/O-bound ingest/materialize (COG reads).
        skip_download: Build labelled windows but skip the S2 download (smoke test).

    Returns:
        The number of windows with materialized imagery (0 if ``skip_download``).
    """
    from riparian.delineation.rslearn_dataset import build, verify_materialized
    from riparian.labels.label_layer import build_extent_labels

    _redirect_temp(dest)
    fc, _stats = build_extent_labels(bbox, reader=reader)
    result = build(dest, SCAFFOLD_CONFIG, bbox, fc)
    logger.info("windows: %d built, %d skipped (no riparian)",
                result.n_windows, result.n_windows_skipped_empty)
    if skip_download:
        logger.info("--skip-download: stopping after windows (no S2 materialize)")
        return 0

    _rslearn("prepare", dest, workers)
    _rslearn("ingest", dest, workers)      # the big download — COG range-reads to the tile store
    _rslearn("materialize", dest, workers)  # clip tile store → per-window GeoTIFFs
    n = verify_materialized(dest)           # never trust materialize's exit code
    logger.info("materialized %d windows", n)
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--reach", choices=sorted(REACHES), help="a named reach")
    group.add_argument("--bbox", nargs=4, type=float, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"),
                       help="an arbitrary AOI in EPSG:4326")
    ap.add_argument("--gdb", help="local NMRipMap File Geodatabase; omit for the live ArcGIS fetch")
    ap.add_argument("--dest", required=True, type=Path, help="dataset root to create")
    ap.add_argument("--workers", type=int, default=8, help="concurrency for ingest/materialize (default 8)")
    ap.add_argument("--skip-download", action="store_true", help="build labelled windows only (smoke test)")
    args = ap.parse_args()

    bbox = tuple(args.bbox) if args.bbox else REACHES[args.reach]
    if args.gdb:
        reader = gdb_reader_factory(args.gdb)
    else:
        from riparian.labels import nmripmap
        reader = nmripmap.fetch_labeled

    n = materialize_reach(args.dest, bbox, reader, workers=args.workers, skip_download=args.skip_download)
    print(f"done: {n} materialized windows in {args.dest}")


if __name__ == "__main__":
    main()
