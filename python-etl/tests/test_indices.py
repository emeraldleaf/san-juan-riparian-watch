"""Unit tests for the spectral-index + texture pure functions (features.py)."""

import numpy as np
import xarray as xr

from riparian.datacube.features import (
    evi,
    kndvi,
    local_texture,
    ndmi,
    ndre,
    ndvi,
    temporal_stats,
)


def _da(vals: list[float]) -> xr.DataArray:
    return xr.DataArray(np.array(vals, dtype=float))


def test_ndvi_basic():
    assert np.isclose(float(ndvi(_da([8.0]), _da([2.0]))[0]), 0.6)


def test_ndvi_bounds():
    assert float(ndvi(_da([10.0]), _da([0.0]))[0]) == 1.0
    assert float(ndvi(_da([0.0]), _da([10.0]))[0]) == -1.0


def test_ndvi_zero_denominator_is_nan():
    assert np.isnan(float(ndvi(_da([0.0]), _da([0.0]))[0]))


def test_ndmi():
    assert np.isclose(float(ndmi(_da([8.0]), _da([4.0]))[0]), 4.0 / 12.0)


def test_ndre():
    assert np.isclose(float(ndre(_da([8.0]), _da([6.0]))[0]), 2.0 / 14.0)


def test_evi_reflectance_formula():
    v = float(evi(_da([0.5]), _da([0.2]), _da([0.1]))[0])
    expected = 2.5 * 0.3 / (0.5 + 6 * 0.2 - 7.5 * 0.1 + 1.0)
    assert np.isclose(v, expected)


def test_kndvi_is_tanh_ndvi_squared():
    v = float(kndvi(_da([8.0]), _da([2.0]))[0])
    assert np.isclose(v, float(np.tanh(0.6**2)))


def test_local_texture_uniform_is_zero():
    arr = np.full((5, 5), 0.5, dtype=np.float32)
    tex = local_texture(arr, window=3)
    assert np.allclose(tex["texture_std"], 0.0, atol=1e-5)
    assert np.allclose(tex["texture_range"], 0.0, atol=1e-5)


def test_local_texture_nonzero_on_gradient():
    arr = np.tile(np.arange(5, dtype=np.float32), (5, 1))
    tex = local_texture(arr, window=3)
    assert tex["texture_range"].max() > 0.0
    assert tex["texture_std"].max() > 0.0


def test_local_texture_keeps_nan():
    arr = np.full((4, 4), 0.5, dtype=np.float32)
    arr[0, 0] = np.nan
    tex = local_texture(arr, window=3)
    assert np.isnan(tex["texture_std"][0, 0])


def test_temporal_stats_produces_stat_vars_and_nonneg_amplitude():
    data = np.array([
        [[0.1, 0.2], [0.3, 0.4]],
        [[0.5, 0.6], [0.7, 0.8]],
        [[0.9, 1.0], [0.2, 0.3]],
    ])
    cube = xr.Dataset({"ndvi": (("time", "y", "x"), data)})
    stats = temporal_stats(cube)
    for suffix in ("median", "p10", "p90", "amplitude"):
        assert f"ndvi_{suffix}" in stats
    assert float(stats["ndvi_amplitude"].min()) >= 0.0
