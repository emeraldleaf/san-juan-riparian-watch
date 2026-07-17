"""Tests for the label layer and its imagery validation.

The tests that matter here are the ones that inject a defect we could plausibly ship — an empty
positive class, an unbalanced layer, desert negatives, and above all a **misregistered label
mask** — and assert that the gate catches it. A validator nobody has ever seen fail is not a
validator.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box

from riparian.labels import label_layer, validate_layer
from riparian.labels.nmripmap import (
    RIPARIAN_WOODY_NATIVE,
    UPLAND,
    LabeledPolygon,
)


def _poly(x: float, y: float, label: str, size: float = 0.01) -> LabeledPolygon:
    return LabeledPolygon(
        geometry=box(x, y, x + size, y + size),
        label=label,
        l2_code="RW" if label == RIPARIAN_WOODY_NATIVE else "UP",
        confidence=1.0,
    )


# --------------------------------------------------------------------------------------------
# The layer
# --------------------------------------------------------------------------------------------


def test_empty_positive_class_is_refused() -> None:
    """A layer with no riparian in it would train happily and learn nothing."""
    polys = [_poly(0.0, 0.0, UPLAND), _poly(0.1, 0.0, UPLAND)]

    with pytest.raises(ValueError, match="empty positive class"):
        label_layer.assemble(polys)


def test_negatives_are_capped_so_the_head_cannot_cheat() -> None:
    """Unbalanced, a segmentation head scores ~90% by predicting 'other' everywhere."""
    polys = [_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE)]
    polys += [_poly(0.1 * i, 0.5, UPLAND) for i in range(40)]

    _, stats = label_layer.assemble(polys, max_negative_ratio=3.0)

    assert stats.n_positive == 1
    assert stats.negative_ratio <= 3.0 + 1e-6, "negatives exceeded the balance cap"
    assert stats.n_negative < 40, "cap did not bite"


def test_negatives_outside_the_corridor_are_dropped() -> None:
    """A negative in the desert teaches 'is it green', which is not the task."""
    corridor = box(-0.01, -0.01, 0.05, 0.05)
    polys = [
        _poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE),
        _poly(0.02, 0.02, UPLAND),  # inside the valley bottom — a hard negative, keep
        _poly(9.0, 9.0, UPLAND),  # far outside — desert, drop
    ]

    fc, stats = label_layer.assemble(polys, corridor=corridor)

    assert stats.dropped_outside_corridor == 1
    assert all(f["properties"]["class"] != 0 for f in fc["features"]), "class 0 must never be emitted"


def test_the_layer_is_deterministic() -> None:
    """A label layer that changes between runs is not a label layer."""
    polys = [_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE)]
    polys += [_poly(0.1 * i, 0.5, UPLAND) for i in range(20)]

    first, _ = label_layer.assemble(polys)
    second, _ = label_layer.assemble(polys)

    assert first == second


def test_the_layer_is_invariant_to_input_order() -> None:
    """fetch_labeled() is a DB/API — its row order must not change the capped-negative selection.

    The seed is fixed, but a seeded shuffle of a differently-ordered list yields a different subset.
    Canonicalizing before sampling is what makes the layer reproducible across fetch orderings.
    """
    polys = [_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE)]
    polys += [_poly(0.1 * i, 0.5, UPLAND) for i in range(40)]

    ordered, _ = label_layer.assemble(polys, max_negative_ratio=3.0)
    reversed_in, _ = label_layer.assemble(list(reversed(polys)), max_negative_ratio=3.0)

    assert ordered == reversed_in, "feature output changed when the input order changed"


def test_a_nonfinite_or_nonpositive_cap_is_refused() -> None:
    """A NaN cap makes the balance test vacuously pass, shipping an unbalanced layer that looks fine."""
    polys = [_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE), _poly(0.1, 0.5, UPLAND)]

    for bad in (float("nan"), 0.0, -1.0):
        with pytest.raises(ValueError, match="finite and positive"):
            label_layer.assemble(polys, max_negative_ratio=bad)


def test_build_extent_labels_uses_the_injected_reader() -> None:
    """The fetch boundary is a Protocol, so it can be exercised offline with a fixture reader."""
    polys = [_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE), _poly(0.02, 0.02, UPLAND)]
    seen: list[tuple[float, float, float, float]] = []

    def fake_reader(bbox: tuple[float, float, float, float]) -> list[LabeledPolygon]:
        seen.append(bbox)
        return polys

    fc, stats = label_layer.build_extent_labels((-1.0, -1.0, 1.0, 1.0), reader=fake_reader)

    assert seen == [(-1.0, -1.0, 1.0, 1.0)], "the injected reader was not called with the bbox"
    assert stats.n_positive == 1
    assert len(fc["features"]) == stats.n_features


def test_features_carry_the_label_vintage() -> None:
    """2020 labels must be fitted on 2020 imagery. We have made the opposite mistake once."""
    fc, _ = label_layer.assemble([_poly(0.0, 0.0, RIPARIAN_WOODY_NATIVE)])

    assert fc["features"][0]["properties"]["label_year"] == 2020


# --------------------------------------------------------------------------------------------
# The imagery validation
# --------------------------------------------------------------------------------------------


def test_auc_is_symmetric_and_calibrated() -> None:
    """Sanity: perfectly separated = 1.0, identical = 0.5."""
    assert validate_layer.auc(np.array([1.0, 2.0]), np.array([-1.0, -2.0])) == pytest.approx(1.0)
    assert validate_layer.auc(np.array([0.0, 0.0]), np.array([0.0, 0.0])) == pytest.approx(0.5)


def test_ties_do_not_bias_the_auc() -> None:
    """A constant band (a cloud-masked region) must not be scored as a win."""
    tied = np.zeros(50)

    assert validate_layer.auc(tied, tied) == pytest.approx(0.5)


def _scene(shift: tuple[int, int] = (0, 0)) -> tuple[np.ndarray, np.ndarray]:
    """An NDVI scene with a green riparian stripe, and a label mask optionally MISREGISTERED."""
    rng = np.random.default_rng(0)
    ndvi = rng.normal(0.08, 0.02, size=(64, 64))  # dry upland
    ndvi[:, 28:36] = rng.normal(0.45, 0.03, size=(64, 8))  # the green corridor

    mask = np.full((64, 64), 4, dtype=int)  # 4 = other
    mask[:, 28:36] = validate_layer.POSITIVE_CLASS

    dy, dx = shift
    mask = np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return ndvi, mask


def test_aligned_labels_pass_both_tests() -> None:
    ndvi, mask = _scene()

    sep = validate_layer.separability(
        ndvi[mask == validate_layer.POSITIVE_CLASS],
        ndvi[np.isin(mask, validate_layer.CORRIDOR_NEGATIVE_CLASSES)],
    )
    align = validate_layer.alignment(ndvi, mask)

    assert sep.verdict != "BROKEN"
    assert align.is_aligned
    assert validate_layer.report(sep, align) is True


def test_the_shift_test_catches_a_misregistration_that_separability_misses() -> None:
    """🔴 THE ONE THAT MATTERS.

    Labels shifted 3 px off the corridor still *correlate* with it — so separability passes and
    would wave the layer through to a GPU. Only the shift test sees that they do not sit ON the
    pixels.
    """
    ndvi, mask = _scene(shift=(0, 3))

    sep = validate_layer.separability(
        ndvi[mask == validate_layer.POSITIVE_CLASS],
        ndvi[np.isin(mask, validate_layer.CORRIDOR_NEGATIVE_CLASSES)],
    )
    align = validate_layer.alignment(ndvi, mask)

    assert not align.is_aligned, "shift test failed to catch a 3px registration bug"
    assert align.best_shift == (0, -3), "shift test found the wrong offset"
    assert validate_layer.report(sep, align) is False, "a misregistered layer reached the GPU gate"


def test_a_straight_corridor_does_not_raise_a_FALSE_registration_alarm() -> None:
    """A reach that runs straight is invariant under translation along its own axis.

    Every offset on that axis scores identically. An arbitrary argmax invents a displacement that
    is not in the data and reports a registration bug on labels that are perfectly aligned —
    sending someone hunting a CRS bug that does not exist. Among equals, no shift must win.

    (This test exists because the first version of `alignment` did exactly that.)
    """
    # The scene is aligned, and its corridor is a vertical stripe, so every dy scores the same.
    ndvi, mask = _scene()

    align = validate_layer.alignment(ndvi, mask)

    assert align.best_shift == (0, 0), "tie among equal-scoring offsets invented a displacement"
    assert align.is_aligned


def test_broken_labels_are_a_hard_stop() -> None:
    """Labels uncorrelated with the imagery: AUC ~0.5. Never train on this."""
    rng = np.random.default_rng(1)
    ndvi = rng.normal(0.2, 0.05, size=(64, 64))
    mask = rng.integers(1, 3, size=(64, 64)) * 3 - 2  # random 1s and 4s

    sep = validate_layer.separability(ndvi[mask == 1], ndvi[mask > 1])

    assert sep.verdict == "BROKEN"


def test_water_is_excluded_from_the_negative_set() -> None:
    """Water is trivially separable from vegetation, so it must not pad the negative set.

    The hard negative is agriculture (class 3): as green as riparian, so NDVI barely separates them.
    Water (class 2) has near-zero NDVI — including it makes the negatives look easy and inflates the
    AUC, which is exactly how a leaky gate passes while the real task (riparian vs agriculture) is
    unsolved. The validator's contract is riparian-vs-corridor, and water is not corridor.
    """
    rng = np.random.default_rng(0)
    ndvi = rng.normal(0.45, 0.02, size=(32, 32))  # riparian, green
    mask = np.full((32, 32), validate_layer.POSITIVE_CLASS, dtype=int)
    ndvi[:, :10] = rng.normal(0.43, 0.02, size=(32, 10))  # agriculture — nearly as green
    mask[:, :10] = 3
    ndvi[:, 10:16] = rng.normal(-0.05, 0.02, size=(32, 6))  # water — obviously not vegetation
    mask[:, 10:16] = 2

    corridor_only = validate_layer.separability(
        ndvi[mask == validate_layer.POSITIVE_CLASS],
        ndvi[np.isin(mask, validate_layer.CORRIDOR_NEGATIVE_CLASSES)],
    )
    with_water = validate_layer.separability(
        ndvi[mask == validate_layer.POSITIVE_CLASS], ndvi[mask > validate_layer.POSITIVE_CLASS]
    )

    assert with_water.auc > corridor_only.auc, "water should inflate the AUC — that is the bug"
    assert 2 not in validate_layer.CORRIDOR_NEGATIVE_CLASSES


def test_a_boundary_touching_label_does_not_wrap_around_the_tile() -> None:
    """A label on the tile edge must not be scored against imagery on the opposite edge.

    `np.roll` wraps; a real registration offset does not. If a corridor sits at the left edge, a
    +x shift with wrapping would slide it onto the (unrelated) right edge and could manufacture a
    misleading score. The padded translation drops what falls off and leaves the exposed border
    unlabeled, so `alignment` still reports the labels as aligned.
    """
    rng = np.random.default_rng(0)
    ndvi = rng.normal(0.08, 0.02, size=(64, 64))
    ndvi[:, :6] = rng.normal(0.45, 0.03, size=(64, 6))  # corridor hard against the left edge
    mask = np.full((64, 64), 4, dtype=int)
    mask[:, :6] = validate_layer.POSITIVE_CLASS

    align = validate_layer.alignment(ndvi, mask)

    assert align.best_shift == (0, 0), "a boundary label wrapped and invented a displacement"
    assert align.is_aligned
