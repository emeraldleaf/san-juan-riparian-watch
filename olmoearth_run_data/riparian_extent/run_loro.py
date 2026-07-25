"""Drive the leave-one-reach-out (LORO) FM fine-tune over the combined dataset.

For a held-out reach this flips ``options.split`` — the reach's windows become ``val``, the other
three become ``train`` — then (with ``--fit``) launches ``rslearn model fit``. ``model.yaml`` is
never edited: its ``val_config`` already selects ``tags: {split: val}``, so the **val metrics are the
held-out-reach transfer metrics**. Read the best ``val riparian AUC`` per fold and compare to the RF
bar (Farmington 0.905 · Aztec/Animas 0.886 · Kirtland 0.845 · Malpais 0.557 · macro 0.798).

Run once per reach to complete the 4-fold LORO. Without ``--fit`` it only sets the split and prints
the exact fit command (so you can eyeball the counts before spending GPU).

Usage:
    PYTHONPATH=../../python-etl python run_loro.py --dest dataset_loro --hold-out malpais [--fit]
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from build_loro_dataset import GROUP, REACHES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("run_loro")


def set_fold(dest: Path, held_out: str) -> tuple[int, int]:
    """Tag the held-out reach's windows ``split=val`` and the rest ``split=train``. Returns (train, val)."""
    from rslearn.dataset import Dataset
    from upath import UPath

    n_train = n_val = 0
    for window in Dataset(UPath(str(dest))).load_windows(groups=[GROUP]):
        is_val = window.options.get("reach") == held_out
        window.options = {**window.options, "split": "val" if is_val else "train"}
        window.save()
        n_val += is_val
        n_train += not is_val
    logger.info("fold hold-out=%s → %d train / %d val windows", held_out, n_train, n_val)
    return n_train, n_val


def _fit_command(dest: Path) -> list[str]:
    """The rslearn fit command for this fold (V1_BASE + per-pixel UNetDecoder, from model.yaml)."""
    return [sys.executable, "-m", "rslearn.main", "model", "fit",
            "--config", str(HERE / "model.yaml"),
            "--data.init_args.path", str(dest)]


def _fit_env(dest: Path, held_out: str) -> dict[str, str]:
    """Environment for the fit — checkpoint dir per fold, sane worker default; wire WANDB_* yourself."""
    env = dict(os.environ)
    env.setdefault("DATASET_PATH", str(dest))
    env.setdefault("CHECKPOINT_PATH", str(HERE / f".tmp/loro/{held_out}"))
    env.setdefault("NUM_WORKERS", "4")
    return env


def main() -> int:
    """Set the LORO split for one held-out reach and optionally launch its fine-tune."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=HERE / "dataset_loro", help="combined LORO dataset")
    ap.add_argument("--hold-out", required=True, choices=sorted(REACHES), help="reach to hold out")
    ap.add_argument("--fit", action="store_true", help="launch rslearn model fit (needs a GPU)")
    a = ap.parse_args()

    set_fold(a.dest, a.hold_out)
    cmd = _fit_command(a.dest)
    if not a.fit:
        logger.info("dry (no --fit). To train this fold:\n  %s", " ".join(cmd))
        return 0
    Path(_fit_env(a.dest, a.hold_out)["CHECKPOINT_PATH"]).mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, env=_fit_env(a.dest, a.hold_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
