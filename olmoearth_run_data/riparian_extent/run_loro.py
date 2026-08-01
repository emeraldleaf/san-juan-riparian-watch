"""Drive the leave-one-reach-out (LORO) FM fine-tune over the combined dataset.

**Unbiased by construction.** The held-out reach is the ``test`` set, scored **once** at the end —
never used to pick the epoch. Epoch selection / early-stopping uses ``val``, which is an internal
hash slice of the *three training reaches* (carried in ``options.cv`` by ``build_loro_dataset.py``).
Selecting the best epoch on the held-out reach and then reporting it would be selection-on-the-test-set
and would not be comparable to the single-shot RF bar. So per fold this sets:

- held-out reach windows → ``split = test``
- the other three reaches → their ``cv`` split (``train`` / ``val``)

then (with ``--fit``) runs ``rslearn model fit`` (train/val) **and** ``rslearn model test`` (held-out).
The **test riparian AUC** is the transfer number — compare to the RF bar (Farmington 0.905 ·
Aztec/Animas 0.886 · Kirtland 0.845 · Malpais 0.557 · macro 0.798).

Run once per reach for the 4-fold LORO. Without ``--fit`` it only sets the split and prints the commands.

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


def set_fold(dest: Path, held_out: str) -> dict[str, int]:
    """Tag the held-out reach ``split=test``; the other three keep their ``cv`` split (train/val).

    Args:
        dest: Combined LORO dataset root.
        held_out: Reach to hold out (its windows become the ``test`` set, scored once).

    Returns:
        Window counts per split, e.g. ``{"train": 953, "val": 123, "test": 328}``.
    """
    from rslearn.dataset import Dataset
    from upath import UPath

    counts = {"train": 0, "val": 0, "test": 0}
    for window in Dataset(UPath(str(dest))).load_windows(groups=[GROUP]):
        is_test = window.options.get("reach") == held_out
        split = "test" if is_test else window.options.get("cv", "train")
        window.options = {**window.options, "split": split}
        window.save()
        counts[split] += 1
    logger.info("fold hold-out=%s → %d train / %d val / %d test", held_out, *counts.values())
    return counts


def _fit_command(dest: Path) -> list[str]:
    """rslearn fit for this fold — trains on the 3 reaches' train/val (V1_BASE + UNetDecoder)."""
    return [sys.executable, "-m", "rslearn.main", "model", "fit",
            "--config", str(HERE / "model.yaml"), "--data.init_args.path", str(dest)]


def _best_checkpoint(ckpt_dir: Path) -> Path:
    """The fit's ``save_top_k=1`` best checkpoint (``epoch=*.ckpt``); falls back to ``last.ckpt``."""
    best = sorted(ckpt_dir.glob("epoch=*.ckpt"))
    if best:
        return best[0]
    if (ckpt_dir / "last.ckpt").exists():
        return ckpt_dir / "last.ckpt"
    raise SystemExit(f"no checkpoint in {ckpt_dir} — did the fit run?")


def _test_command(dest: Path, ckpt: Path) -> list[str]:
    """rslearn test on the held-out reach, **loading the fit's checkpoint** — the unbiased score.

    Without ``--ckpt_path`` a separate ``model test`` process scores freshly-initialised weights
    (an untrained decoder), which is meaningless — so the trained checkpoint is passed explicitly.
    """
    return [sys.executable, "-m", "rslearn.main", "model", "test",
            "--config", str(HERE / "model.yaml"), "--data.init_args.path", str(dest),
            "--ckpt_path", str(ckpt)]


def _fit_env(dest: Path, held_out: str) -> dict[str, str]:
    """Environment for the fit — checkpoint dir per fold, sane worker default; wire WANDB_* yourself."""
    env = dict(os.environ)
    env.setdefault("DATASET_PATH", str(dest))
    env.setdefault("CHECKPOINT_PATH", str(HERE / f".tmp/loro/{held_out}"))
    env.setdefault("NUM_WORKERS", "4")
    env.setdefault("PREDICTION_OUTPUT_LAYER", "output")  # model.yaml's RslearnWriter needs it, even for fit
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
    env = _fit_env(a.dest, a.hold_out)
    ckpt_dir = Path(env["CHECKPOINT_PATH"])
    if not a.fit:
        logger.info("dry (no --fit). This fold trains on 3 reaches, then tests the held-out one:\n  %s",
                    " ".join(_fit_command(a.dest)))
        return 0
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(_fit_command(a.dest), check=True, env=env)                 # train/val on the 3 reaches
    subprocess.run(_test_command(a.dest, _best_checkpoint(ckpt_dir)),         # score the held-out reach ONCE,
                   check=True, env=env)                                       # from the fit's best checkpoint
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
