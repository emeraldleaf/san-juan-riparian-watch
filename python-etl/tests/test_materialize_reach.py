"""Unit tests for the reusable reach-cube materializer (``materialize_reach.py``).

The module lives in ``olmoearth_run_data/riparian_extent/`` (an ops script tree, not
the ``riparian`` package), so these tests import it by prepending that directory to
``sys.path``. Its heavy top-level dependency — ``validate_reach``, which imports the
geo stack (planetary_computer/pystac/rasterio/pyproj) — is stubbed, and the pipeline
functions it calls at run time (``rslearn`` build/ingest/materialize) are faked, so
the tests exercise the **orchestration logic** ($0, no network, no GPU): the
``--skip-download`` short-circuit, the no-windows short-circuit, the full step order,
and CLI argument resolution.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

REACH_DIR = Path(__file__).resolve().parents[2] / "olmoearth_run_data" / "riparian_extent"
MALPAIS_BBOX = (-108.8217, 36.8096, -108.6729, 36.9508)
FARMINGTON_BBOX = (-108.40, 36.66, -108.10, 36.80)


@pytest.fixture
def mr(monkeypatch):
    """Import ``materialize_reach`` with ``validate_reach`` stubbed out."""
    fake_vr = types.ModuleType("validate_reach")
    fake_vr.FARMINGTON_BBOX = FARMINGTON_BBOX
    fake_vr.MALPAIS_BBOX = MALPAIS_BBOX
    fake_vr.gdb_reader_factory = lambda path: ("gdb_reader", path)
    monkeypatch.setitem(sys.modules, "validate_reach", fake_vr)
    monkeypatch.syspath_prepend(str(REACH_DIR))
    monkeypatch.delitem(sys.modules, "materialize_reach", raising=False)
    import materialize_reach

    # _redirect_temp mutates os.environ + touches the disk — neither is under test.
    monkeypatch.setattr(materialize_reach, "_redirect_temp", lambda dest: None)
    return materialize_reach


def _fake_pipeline(monkeypatch, mr, n_windows):
    """Fake the function-local ``riparian`` imports and ``subprocess`` for one run.

    Returns the ``(build, verify, run)`` mocks so a test can assert on call counts
    and argument order.
    """
    build = MagicMock(
        return_value=SimpleNamespace(n_windows=n_windows, n_windows_skipped_empty=0)
    )
    verify = MagicMock(return_value=n_windows)
    build_labels = MagicMock(
        return_value=({"type": "FeatureCollection", "features": []}, {})
    )

    rls_mod = types.ModuleType("riparian.delineation.rslearn_dataset")
    rls_mod.build = build
    rls_mod.verify_materialized = verify
    ll_mod = types.ModuleType("riparian.labels.label_layer")
    ll_mod.build_extent_labels = build_labels

    # The whole parent chain must be present so ``from a.b.c import x`` resolves
    # to the fakes without importing the real (rslearn/torch-heavy) modules.
    for name, mod in (
        ("riparian", types.ModuleType("riparian")),
        ("riparian.delineation", types.ModuleType("riparian.delineation")),
        ("riparian.delineation.rslearn_dataset", rls_mod),
        ("riparian.labels", types.ModuleType("riparian.labels")),
        ("riparian.labels.label_layer", ll_mod),
    ):
        monkeypatch.setitem(sys.modules, name, mod)

    run = MagicMock()
    monkeypatch.setattr(mr.subprocess, "run", run)
    return build, verify, run


def test_full_pipeline_runs_all_steps_in_order(mr, monkeypatch, tmp_path):
    build, verify, run = _fake_pipeline(monkeypatch, mr, n_windows=3)

    n = mr.materialize_reach(tmp_path / "ds", MALPAIS_BBOX, ("reader",), workers=4)

    assert n == 3
    build.assert_called_once()
    verify.assert_called_once()
    steps = [call.args[0][4] for call in run.call_args_list]  # cmd[4] is the step
    assert steps == ["prepare", "ingest", "materialize"]


def test_skip_download_stops_after_windows(mr, monkeypatch, tmp_path):
    build, verify, run = _fake_pipeline(monkeypatch, mr, n_windows=5)

    n = mr.materialize_reach(
        tmp_path / "ds", MALPAIS_BBOX, ("reader",), skip_download=True
    )

    assert n == 0
    run.assert_not_called()
    verify.assert_not_called()


def test_no_windows_short_circuits(mr, monkeypatch, tmp_path):
    build, verify, run = _fake_pipeline(monkeypatch, mr, n_windows=0)

    n = mr.materialize_reach(tmp_path / "ds", MALPAIS_BBOX, ("reader",))

    assert n == 0
    run.assert_not_called()
    verify.assert_not_called()


def test_main_resolves_named_reach_to_its_bbox(mr, monkeypatch, tmp_path):
    captured = {}

    def _capture(dest, bbox, reader, workers=8, skip_download=False):
        captured.update(dest=dest, bbox=bbox, reader=reader)
        return 0

    monkeypatch.setattr(mr, "materialize_reach", _capture)
    monkeypatch.setattr(
        sys, "argv",
        ["materialize_reach", "--reach", "malpais",
         "--gdb", "some.gdb", "--dest", str(tmp_path / "ds")],
    )

    mr.main()

    assert captured["bbox"] == MALPAIS_BBOX
    assert captured["reader"] == ("gdb_reader", "some.gdb")


def test_main_requires_reach_or_bbox(mr, monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["materialize_reach", "--dest", str(tmp_path / "ds")]
    )

    with pytest.raises(SystemExit):
        mr.main()
