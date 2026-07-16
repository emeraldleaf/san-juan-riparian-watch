"""Derive a laptop dry-run config from the canonical ``model.yaml``.

Phase 0, step 4 of ``docs/specs/2026-07-12-gpu-finetune-execution-plan.md``: prove the pipeline
runs one epoch on CPU/MPS with a finite, decreasing loss — before renting a GPU. This script keeps
the dry-run FAITHFUL to the real config (it loads ``model.yaml`` and overrides the minimum) so the
smoke test exercises the same wiring the GPU run will, not a hand-built lookalike.

The overrides are exactly the deltas the dry-run needs, each one a finding the dry-run surfaced:

  model_id   OLMOEARTH_V1_1_BASE -> OLMOEARTH_V1_NANO
             The v1.1 id does not resolve in this rslearn (only V1_{NANO,TINY,BASE,LARGE}); the
             canonical config's own comment predicted this. NANO also fits a laptop.
  in_channels 768 -> 128
             The pooling decoder's in_channels must match the encoder embedding. 768 is BASE; NANO
             emits 128. A silent mismatch on a GPU; a $0 fix here.
  decoder    SegmentationPoolingDecoder -> riparian.delineation.decoders.TemporalSegmentationPoolingDecoder
             The stock decoder reads spatial dims as image.shape[1:3], which on our 4-D
             [bands, timesteps, H, W] phenology cube grabs (timesteps, H). The adapter reads the
             true last-two axes. See that module for the full account.
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
ADAPTER_DECODER = "riparian.delineation.decoders.TemporalSegmentationPoolingDecoder"


def build(dataset_path: str, epochs: int, log_dir: str) -> dict:
    """Load the canonical config and apply the dry-run overrides."""
    cfg = yaml.safe_load(CANONICAL.read_text())

    mi = cfg["model"]["init_args"]["model"]["init_args"]
    enc = mi["encoder"][0]["init_args"]
    enc["model_id"] = "OLMOEARTH_V1_NANO"

    dec = mi["decoders"]["riparian_classification"][0]
    dec["class_path"] = ADAPTER_DECODER
    dec["init_args"]["in_channels"] = NANO_EMBEDDING

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
