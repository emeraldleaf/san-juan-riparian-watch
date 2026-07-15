"""The label crosswalk and the model's num_classes must agree — mechanically.

This test exists because they did NOT agree, and the dry-run paid to find it: the crosswalk emits
four real classes (riparian=1, water=2, agriculture=3, other=4), but ``model.yaml`` declared
``num_classes: 4``. With ``zero_is_invalid: true``, class 0 is the ignored label, so ``num_classes``
must be ``max_class_id + 1`` — five, not four. Training crashed with ``Target 4 is out of bounds``
inside the sanity check.

The scaffold was authored for an earlier three-class scheme (riparian/water/other) and its
``num_classes`` was never updated when agriculture was split out. Prose drift a human would miss;
an off-by-one a GPU would have hit on step one. Now it is a unit test.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from riparian.labels.nmripmap import PHASE1_CLASS_IDS

MODEL_YAML = Path(__file__).resolve().parents[2] / "olmoearth_run_data/riparian_extent/model.yaml"


def _num_classes(cfg: dict) -> int:
    task = cfg["data"]["init_args"]["task"]["init_args"]["tasks"]["riparian_classification"]["init_args"]
    return task["num_classes"]


def _decoder_out_channels(cfg: dict) -> int:
    mi = cfg["model"]["init_args"]["model"]["init_args"]
    return mi["decoders"]["riparian_classification"][0]["init_args"]["out_channels"]


def test_num_classes_covers_every_crosswalk_class() -> None:
    """num_classes must be max(class id) + 1, because class 0 is the zero_is_invalid ignore label."""
    cfg = yaml.safe_load(MODEL_YAML.read_text())
    max_class_id = max(PHASE1_CLASS_IDS.values())
    required = max_class_id + 1  # +1 for the class-0 slot

    assert _num_classes(cfg) >= required, (
        f"crosswalk emits classes up to {max_class_id}, so num_classes must be >= {required} "
        f"(class 0 is the zero_is_invalid ignore label); model.yaml has {_num_classes(cfg)}. "
        f"A label of {max_class_id} would be 'out of bounds' at training step one."
    )


def test_decoder_out_channels_matches_num_classes() -> None:
    """The segmentation head emits one channel per class; a mismatch is a silent training bug."""
    cfg = yaml.safe_load(MODEL_YAML.read_text())

    assert _decoder_out_channels(cfg) == _num_classes(cfg), (
        f"decoder out_channels ({_decoder_out_channels(cfg)}) must equal num_classes "
        f"({_num_classes(cfg)}) — the head produces one logit per class."
    )
