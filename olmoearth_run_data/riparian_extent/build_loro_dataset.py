"""Combine the 4 reach datasets into one leave-one-reach-out (LORO) dataset for the FM run.

The RF bar (#71) was measured **leave-one-reach-out** over Farmington/Malpais/Kirtland/Aztec-Animas.
To score the foundation model on the *same footing*, rslearn needs those 4 reaches in **one** dataset
so a single ``model fit`` can hold one reach out. This hardlinks each reach's materialized windows
into a combined dataset under the group ``san_juan_nmripmap`` (what ``model.yaml`` selects), tags every
window with its ``reach``, then rasterizes the vector labels into the ``label_raster`` training target.

**Hardlinks, not copies** — the four reaches are ~53 GB; copying would double that. Only the small
``metadata.json`` is written fresh per window (group + reach tag); the big GeoTIFFs are shared inodes
on the same filesystem, so the combined dataset costs ~no extra space.

Per-fold train/val is set later by ``run_loro.py`` flipping ``options.split`` by reach — ``model.yaml``
never changes (its ``train_config``/``val_config`` already select ``tags: {split: train|val}``).

Usage:
    PYTHONPATH=../../python-etl python build_loro_dataset.py --dest dataset_loro
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from riparian.delineation.rslearn_dataset import (  # noqa: E402
    rasterize_labels_and_split,
    verify_materialized,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("build_loro")

GROUP = "san_juan_nmripmap"  # the window group model.yaml's train/val/test configs select
_META = "metadata.json"
# reach name -> its per-reach dataset dir (the RF-bar footing; bboxes match deploy_extent_map.py)
REACHES = {
    "farmington": "dataset",
    "malpais": "dataset_malpais",
    "kirtland": "dataset_kirtland",
    "aztec_animas": "dataset_aztec_animas",
}


def _hardlink_window(src: Path, dst: Path, reach: str) -> None:
    """Hardlink a window's layer files into ``dst``; write fresh metadata (group + reach tag)."""
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name == _META:
                continue  # written fresh below, not shared — editing must not touch the source
            link = dst / rel / name
            if not link.exists():
                os.link(Path(root) / name, link)
    meta = json.loads((src / _META).read_text())
    meta["group"] = GROUP
    meta["name"] = dst.name  # rslearn rebuilds paths from name — must match the reach-prefixed dir
    meta["options"] = {**meta.get("options", {}), "reach": reach}
    (dst / _META).write_text(json.dumps(meta))


def _combine(dest: Path) -> int:
    """Hardlink every reach's windows into ``dest`` under one group, each tagged by reach."""
    n = 0
    for reach, ds in REACHES.items():
        src_group = HERE / ds / "windows" / "train"
        windows = sorted(w for w in src_group.iterdir() if w.is_dir())
        for win in windows:
            _hardlink_window(win, dest / "windows" / GROUP / f"{reach}__{win.name}", reach)
        n += len(windows)
        logger.info("linked %d %s windows from %s", len(windows), reach, ds)
    return n


def _assert_same_device(dest: Path) -> None:
    """Hardlinks need one filesystem — fail early if any reach dir is on a different device than dest."""
    dev = dest.stat().st_dev
    for ds in REACHES.values():
        if (HERE / ds).stat().st_dev != dev:
            raise SystemExit(f"{HERE / ds} is on a different filesystem than {dest}; os.link cannot "
                             f"cross devices. Put --dest on the same drive as the reach datasets.")


def _tag_cv(dest: Path) -> None:
    """Preserve each window's train/val hash split as ``options['cv']`` — run_loro flips it per fold."""
    from rslearn.dataset import Dataset
    from upath import UPath

    for window in Dataset(UPath(str(dest))).load_windows(groups=[GROUP]):
        window.options = {**window.options, "cv": window.options.get("split", "train")}
        window.save()


def main() -> int:
    """Build the combined LORO dataset: hardlink 4 reaches, rasterize labels, preserve the CV split.

    Side effects: creates ``--dest``, hardlinks ~53 GB of GeoTIFFs into it, writes label rasters, and
    tags each window with ``reach`` + ``cv`` (the train/val hash slice run_loro flips per fold).

    Returns:
        Process exit code (``0`` on success).
    """
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=HERE / "dataset_loro", help="combined dataset root")
    a = ap.parse_args()

    (a.dest / "windows").mkdir(parents=True, exist_ok=True)
    _assert_same_device(a.dest)  # hardlinks fail across devices — check before writing anything
    shutil.copy(HERE / "dataset" / "config.json", a.dest / "config.json")  # identical across reaches
    n = _combine(a.dest)
    logger.info("combined %d windows into %s (group=%s)", n, a.dest, GROUP)
    rasterize_labels_and_split(a.dest, group=GROUP)  # writes label_raster + a train/val hash split
    _tag_cv(a.dest)  # freeze that hash split as options['cv'] before per-fold retagging
    verify_materialized(a.dest, group=GROUP)
    print(f"done: {n} windows in {a.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
