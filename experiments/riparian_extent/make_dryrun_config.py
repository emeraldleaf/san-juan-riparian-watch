"""Derive a laptop dry-run config from the canonical ``model.yaml``.

Phase 0, step 4 of ``docs/specs/2026-07-12-gpu-finetune-execution-plan.md``: prove the pipeline
runs one epoch on CPU/MPS with a finite, decreasing loss — before renting a GPU. This script keeps
the dry-run FAITHFUL to the real config (it loads ``model.yaml`` and overrides the minimum) so the
smoke test exercises the same wiring the GPU run will, not a hand-built lookalike.

The overrides are exactly the deltas the dry-run needs, each one a finding the dry-run surfaced:

  model_id   OLMOEARTH_V1_BASE -> OLMOEARTH_V1_NANO
             NANO fits a laptop. (V1_BASE is the canonical Phase-1 model, #44; the non-resolving
             V1_1_BASE was retired there.)
  in_channels [[2, 768]] -> [[2, 128]]
             UNetDecoder's in_channels is a list of (downsample-factor, channels): the encoder emits
             one feature map at 1/patch_size (factor 2). 768 is V1_BASE's embedding; NANO emits 128.
             Only the channel count changes — no class_path override, since UNetDecoder (unlike the
             old pooling decoder) reads the encoder FeatureMaps, not the raw image.
  trainer    CPU, single device, no DDP, CSVLogger not W&B, few epochs
             A laptop has no DDP and no W&B project. FreezeUnfreeze STAYS: it keeps the encoder
             frozen until epoch 20, so the dry-run trains only the decoder and never needs the
             olmo-core training extra (which is not installed — inference-only mode).

NOT overridden, because they are real fixes that belong in the canonical config and are already
there: num_classes 4 -> 5 (four real classes + zero_is_invalid's ignored class 0) and the
label_raster target layer. If you find yourself overriding those here, fix model.yaml instead.

Usage:
    python make_dryrun_config.py <dataset_path> <out.yaml> [--epochs N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).parent
CANONICAL = HERE / "model.yaml"

NANO_EMBEDDING = 128
PATCH_FACTOR = 2  # the encoder emits one feature map at 1/patch_size resolution


def build(dataset_path: str, epochs: int, log_dir: str) -> dict:
    """Load the canonical config and apply the dry-run overrides."""
    cfg = yaml.safe_load(CANONICAL.read_text())

    mi = cfg["model"]["init_args"]["model"]["init_args"]
    enc = mi["encoder"][0]["init_args"]
    enc["model_id"] = "OLMOEARTH_V1_NANO"

    # The canonical decoder is UNetDecoder(in_channels=[[2, 768]]) for V1_BASE. NANO's embedding is
    # 128, so only the channel count changes — UNetDecoder consumes the encoder's FeatureMaps and has
    # none of the raw-image shape assumptions that forced the old pooling-decoder adapter, so no
    # class_path override is needed.
    dec = mi["decoders"]["riparian_classification"][0]
    dec["init_args"]["in_channels"] = [[PATCH_FACTOR, NANO_EMBEDDING]]

    data = cfg["data"]["init_args"]
    data["path"] = dataset_path
    data["batch_size"] = 4
    data["num_workers"] = 0
    for key in ("train_config", "val_config", "test_config"):
        data[key]["init_args"]["groups"] = ["train"]
    data["inputs"]["label"]["init_args"]["layers"] = ["label_raster"]

    tr = cfg["trainer"]
    tr["accelerator"] = "cpu"
    tr["strategy"] = "auto"
    tr["devices"] = 1
    tr["max_epochs"] = epochs
    tr["log_every_n_steps"] = 1
    tr["logger"] = {
        "class_path": "lightning.pytorch.loggers.CSVLogger",
        "init_args": {"save_dir": log_dir, "name": "dryrun"},
    }
    tr["callbacks"] = [
        cb for cb in tr["callbacks"] if not cb["class_path"].endswith("RslearnWriter")
    ]
    for cb in tr["callbacks"]:
        if cb["class_path"].endswith("ModelCheckpoint"):
            cb["init_args"]["dirpath"] = str(Path(log_dir) / "ckpt")

    return cfg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_path")
    ap.add_argument("out")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--log-dir", default=".tmp/dryrun")
    args = ap.parse_args()

    cfg = build(str(Path(args.dataset_path).resolve()), args.epochs, str(Path(args.log_dir).resolve()))
    Path(args.out).write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(f"wrote {args.out} (epochs={args.epochs})")


if __name__ == "__main__":
    main()
