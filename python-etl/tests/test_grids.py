"""Unit tests for grid / spatial helpers (stac, invasive, reference, weak_labels)."""

import numpy as np
import xarray as xr

from riparian.datacube.stac import spatial_dims
from riparian.delineation.weak_labels import near_water_mask
from riparian.health.invasive import grid_shape as inv_grid_shape
from riparian.validation.reference import grid_shape as ref_grid_shape


def test_spatial_dims_geographic():
    ds = xr.Dataset({"b": (("latitude", "longitude"), np.zeros((2, 2)))})
    assert spatial_dims(ds) == ("latitude", "longitude")


def test_spatial_dims_projected():
    ds = xr.Dataset({"b": (("y", "x"), np.zeros((2, 2)))})
    assert spatial_dims(ds) == ("y", "x")


def test_grid_shape_unit_cell():
    # 1° bbox at 111_320 m/px → exactly 1×1
    assert inv_grid_shape((0.0, 0.0, 1.0, 1.0), 111_320.0) == (1, 1)
    assert ref_grid_shape((0.0, 0.0, 1.0, 1.0), 111_320.0) == (1, 1)


def test_grid_shape_agrees_across_modules():
    bbox = (-108.0, 37.0, -107.9, 37.1)
    assert inv_grid_shape(bbox, 20.0) == ref_grid_shape(bbox, 20.0)


def test_grid_shape_finer_resolution_more_pixels():
    bbox = (-108.0, 37.0, -107.9, 37.1)
    h20, w20 = inv_grid_shape(bbox, 20.0)
    h10, w10 = inv_grid_shape(bbox, 10.0)
    assert h10 > h20 and w10 > w20


def test_near_water_mask_expands_to_neighbours():
    water = np.zeros((5, 5), dtype=bool)
    water[2, 2] = True
    mask = near_water_mask(water, resolution_m=10.0, dist_m=15.0)
    assert mask[2, 2]                   # the water cell itself
    assert mask[1, 2] and mask[2, 1]    # orthogonal neighbours (10 m ≤ 15 m)
    assert not mask[0, 0]               # far corner (~28 m > 15 m)


def test_near_water_mask_empty_when_no_water():
    water = np.zeros((4, 4), dtype=bool)
    assert not near_water_mask(water, 10.0, 100.0).any()
