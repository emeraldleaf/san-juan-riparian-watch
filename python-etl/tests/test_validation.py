"""Unit tests for validation metrics + spatial-fold assignment."""

import numpy as np
from shapely.geometry import box

from riparian.delineation.validate import assign_spatial_folds
from riparian.validation.reference import compare_masks, rasterize_mask


def test_compare_masks_known_metrics():
    reference = np.array([[1, 1], [1, 1]], dtype=bool)   # 4 riparian
    prediction = np.array([[1, 1], [0, 0]], dtype=bool)  # 2, both correct
    r = compare_masks(reference, prediction, "test")
    assert np.isclose(r.iou, 0.5)          # 2 ∩ / 4 ∪
    assert np.isclose(r.precision, 1.0)    # no false positives
    assert np.isclose(r.recall, 0.5)       # found 2 of 4
    assert np.isclose(r.f1, 2.0 / 3.0)


def test_compare_masks_disjoint_is_zero():
    reference = np.array([[1, 0]], dtype=bool)
    prediction = np.array([[0, 1]], dtype=bool)
    r = compare_masks(reference, prediction, "t")
    assert r.iou == 0.0 and r.precision == 0.0 and r.recall == 0.0


def test_compare_masks_perfect():
    m = np.array([[1, 0], [0, 1]], dtype=bool)
    r = compare_masks(m, m, "t")
    assert r.iou == 1.0 and r.precision == 1.0 and r.recall == 1.0 and r.f1 == 1.0


def test_rasterize_mask_partial_coverage():
    # box covering the left half of a 4×4 unit grid
    mask = rasterize_mask([box(0, 0, 2, 4)], (0, 0, 4, 4), (4, 4))
    assert mask.any() and not mask.all()
    assert int(mask.sum()) == 8            # left 2 columns × 4 rows


def test_rasterize_mask_empty_geoms():
    assert not rasterize_mask([], (0, 0, 1, 1), (2, 2)).any()


def test_assign_spatial_folds_separates_distant_points():
    lats = np.array([37.0, 38.5])
    lons = np.array([-108.0, -107.0])
    folds = assign_spatial_folds(lats, lons, block_deg=0.5)
    assert folds[0] != folds[1]


def test_assign_spatial_folds_groups_nearby_points():
    lats = np.array([37.01, 37.02])
    lons = np.array([-108.01, -108.02])
    folds = assign_spatial_folds(lats, lons, block_deg=1.0)
    assert folds[0] == folds[1]
