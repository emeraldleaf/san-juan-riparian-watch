"""Tests for the reach-block bootstrap CI (pure function, no I/O)."""

import pytest

from riparian.validation.reach_block_bootstrap import (
    LORO_AUROC,
    reach_block_bootstrap,
)


class TestReachBlockBootstrap:
    def test_recorded_loro_interval_includes_zero(self) -> None:
        """The published n=4 comparison is not significant; this pins that verdict."""
        deltas = [fm - rf for fm, rf in LORO_AUROC.values()]
        result = reach_block_bootstrap(deltas)
        assert result.point_estimate == pytest.approx(0.0735, abs=1e-4)
        assert result.ci_low == pytest.approx(-0.023, abs=1e-3)
        assert result.ci_high == pytest.approx(0.246, abs=1e-3)
        assert result.prob_positive == pytest.approx(0.70, abs=1e-2)
        assert result.ci_low < 0.0 < result.ci_high
        assert not result.significant

    def test_reproducible_with_fixed_seed(self) -> None:
        deltas = [0.3, -0.01, -0.03, 0.01]
        a = reach_block_bootstrap(deltas, n_resamples=20_000, seed=7)
        b = reach_block_bootstrap(deltas, n_resamples=20_000, seed=7)
        assert (a.ci_low, a.ci_high, a.prob_positive) == (b.ci_low, b.ci_high, b.prob_positive)

    def test_uniformly_positive_deltas_are_significant(self) -> None:
        result = reach_block_bootstrap([0.05, 0.06, 0.04, 0.07], n_resamples=20_000)
        assert result.significant
        assert result.prob_positive == 1.0

    def test_rejects_fewer_than_two_reaches(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            reach_block_bootstrap([0.1])

    @pytest.mark.parametrize("n_resamples", [0, -1, -100])
    def test_rejects_nonpositive_resamples(self, n_resamples: int) -> None:
        with pytest.raises(ValueError, match="n_resamples must be positive"):
            reach_block_bootstrap([0.1, 0.2], n_resamples=n_resamples)

    @pytest.mark.parametrize("alpha", [0.0, 1.0, -0.05, 1.5])
    def test_rejects_alpha_outside_unit_interval(self, alpha: float) -> None:
        with pytest.raises(ValueError, match="alpha must be in"):
            reach_block_bootstrap([0.1, 0.2], alpha=alpha)
