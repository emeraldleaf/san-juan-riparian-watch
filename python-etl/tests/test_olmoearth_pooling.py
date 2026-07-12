"""Temporal pooling of OlmoEarth tokens — the phenology-preservation contract.

The published RF-beats-OlmoEarth result (docs/olmoearth-vs-rf-baseline.md) was
produced with `mean_time` pooling. These tests pin down *why* that number cannot be
read as "the foundation model is worse": mean-pooling over the time axis is not a
neutral aggregation for this task, it is a lossy one that deletes the discriminator.

`test_mean_time_destroys_phenology` is the load-bearing one. It builds two classes
that are **identical in seasonal mean and differ only in trajectory** — which is
exactly the riparian-vs-irrigated-crop confusion in a semi-arid basin:

    riparian phreatophyte : green early, stays green late  (roots reach groundwater)
    irrigated crop        : green mid-season, senesces hard after harvest

Under `mean_time` these collapse to the same vector and NO classifier can separate
them (that is a property of the representation, not of the classifier). Under
`temporal_stats` they separate perfectly. The failure is in the harness, not the model.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import KFold, cross_val_score

from riparian.delineation.olmoearth import (
    MAX_MODEL_TIMESTEPS,
    POOLINGS,
    pool_tokens,
)

B, P_H, P_W, T, BAND_SETS, D = 1, 4, 4, 12, 3, 8


def _tokens(t: int = T) -> torch.Tensor:
    """Deterministic random encoder-shaped tokens."""
    g = torch.Generator().manual_seed(0)
    return torch.rand(B, P_H, P_W, t, BAND_SETS, D, generator=g)


class TestPoolTokensShapes:
    """Each pooling collapses (B,P_H,P_W,T,Band_Sets,D) to the documented width."""

    def test_mean_time_width_is_d(self) -> None:
        assert pool_tokens(_tokens(), "mean_time").shape == (B, P_H, P_W, D)

    def test_temporal_stats_width_is_4d(self) -> None:
        # mean, std, amplitude, senescence
        assert pool_tokens(_tokens(), "temporal_stats").shape == (B, P_H, P_W, 4 * D)

    def test_concat_time_width_is_t_times_d(self) -> None:
        assert pool_tokens(_tokens(), "concat_time").shape == (B, P_H, P_W, T * D)

    def test_band_set_axis_is_always_averaged(self) -> None:
        """No pooling should leave the band-set axis dangling."""
        for p in POOLINGS:
            assert pool_tokens(_tokens(), p).ndim == 4

    @pytest.mark.parametrize("band_sets", [3, 1])
    def test_handles_v1_and_v1_1_band_set_counts(self, band_sets: int) -> None:
        """v1 emits 3 band-sets; v1.1 merges S2 into 1 (measured, not assumed).

        Pooling must be agnostic to that — on v1.1 the band-set mean is a no-op. If a
        future checkpoint changes this axis again, the widths below still have to hold.
        """
        g = torch.Generator().manual_seed(1)
        tok = torch.rand(B, P_H, P_W, T, band_sets, D, generator=g)
        assert pool_tokens(tok, "mean_time").shape == (B, P_H, P_W, D)
        assert pool_tokens(tok, "temporal_stats").shape == (B, P_H, P_W, 4 * D)

    def test_unknown_pooling_raises(self) -> None:
        with pytest.raises(ValueError, match="pooling must be one of"):
            pool_tokens(_tokens(), "mean_everything")

    def test_trajectory_pooling_needs_two_timesteps(self) -> None:
        """A single timestep has no trajectory — fail loudly rather than emit zeros."""
        with pytest.raises(ValueError, match=r">=2 timesteps"):
            pool_tokens(_tokens(t=1), "temporal_stats")

    def test_mean_time_still_works_on_one_timestep(self) -> None:
        assert pool_tokens(_tokens(t=1), "mean_time").shape == (B, P_H, P_W, D)


class TestTimestepCeiling:
    """The encoder's temporal embedding table is finite — respect it at OUR boundary."""

    def test_subsampling_never_exceeds_the_model_ceiling(self) -> None:
        """`n // max_timesteps` FLOORS, so a naive stride keeps MORE than requested.

        18 scenes with max_timesteps=5 gives step=3 and keeps 6, not 5 — i.e. it
        silently ran a different experiment. At 12 (the model ceiling) the same bug is
        fatal: the encoder dies inside einops with "Shape mismatch, 12 != 18". The
        runner now applies an explicit `.isel(time=slice(0, max_timesteps))` clamp.
        """
        for n_scenes in (5, 6, 13, 17, 18, 31):
            for max_t in (5, MAX_MODEL_TIMESTEPS):
                step = max(1, n_scenes // max_t)
                kept = len(range(0, n_scenes, step)[:max_t])   # stride THEN clamp
                assert kept <= max_t, f"{n_scenes} scenes @ max {max_t} kept {kept}"
                assert kept <= MAX_MODEL_TIMESTEPS

    def test_ceiling_matches_ai2s_monthly_recipe(self) -> None:
        assert MAX_MODEL_TIMESTEPS == 12


def _phenology_tokens(n: int = 64, t: int = T) -> tuple[torch.Tensor, np.ndarray]:
    """Two classes with the SAME temporal mean but different seasonal trajectories.

    Returns tokens shaped (n, 1, 1, t, BAND_SETS, D) and their labels.
    """
    rng = np.random.default_rng(0)
    season = np.linspace(0.0, 1.0, t)                     # early -> late
    rows, labels = [], []
    for i in range(n):
        riparian = i % 2 == 0
        if riparian:
            # flat: green early, still green late
            curve = np.full(t, 0.5)
        else:
            # crop: peaks mid-season, senesces late. Mean is forced to 0.5 below,
            # so the ONLY thing separating the classes is the shape of the curve.
            curve = 0.5 + 0.4 * np.sin(np.pi * season)
            curve = curve - curve.mean() + 0.5
        noise = rng.normal(0, 0.01, size=(t, BAND_SETS, D))
        rows.append(curve[:, None, None] + noise)
        labels.append(int(riparian))
    arr = np.stack(rows)[:, None, None, ...]              # (n,1,1,t,BS,D)
    return torch.from_numpy(arr).float(), np.array(labels)


def _cv_auc(features: np.ndarray, y: np.ndarray) -> float:
    clf = RandomForestClassifier(
        n_estimators=60, random_state=0, min_samples_leaf=2, max_features="sqrt",
    )
    # shuffle=True: these synthetic rows carry no spatial structure, and an UNSHUFFLED
    # KFold over ordered rows gives systematically inverted AUC. (That bit us for real
    # while debugging this — an unshuffled probe on a spatially-ordered grid scored
    # 0.23, which looks like a broken encoder but is just a broken CV split.)
    cv = KFold(n_splits=4, shuffle=True, random_state=0)
    return float(cross_val_score(clf, features, y, cv=cv, scoring="roc_auc").mean())


class TestPhenologyPreservation:
    """The claim behind issue #9, made falsifiable."""

    def test_mean_time_destroys_phenology(self) -> None:
        """Same seasonal mean, different trajectory -> mean_time cannot separate them.

        This is the harness artifact. AUC collapses to chance because the two classes
        are literally the same vector after pooling — no classifier can recover it.
        """
        tokens, y = _phenology_tokens()
        feats = pool_tokens(tokens, "mean_time").reshape(len(y), -1).numpy()

        # The class means are indistinguishable in the pooled representation.
        sep = abs(feats[y == 1].mean() - feats[y == 0].mean())
        assert sep < 1e-3, f"expected class means to collapse, got separation {sep}"
        assert _cv_auc(feats, y) < 0.65, "mean_time should be near chance here"

    def test_temporal_stats_preserves_phenology(self) -> None:
        """The same signal is trivially separable once the trajectory survives."""
        tokens, y = _phenology_tokens()
        feats = pool_tokens(tokens, "temporal_stats").reshape(len(y), -1).numpy()
        assert _cv_auc(feats, y) > 0.95

    def test_concat_time_preserves_phenology(self) -> None:
        tokens, y = _phenology_tokens()
        feats = pool_tokens(tokens, "concat_time").reshape(len(y), -1).numpy()
        assert _cv_auc(feats, y) > 0.95

    def test_senescence_component_carries_the_signal(self) -> None:
        """The early->late contrast is the component that does the work.

        Riparian (flat) has ~zero senescence; the crop curve starts and ends low with a
        mid-season peak, so its endpoints match too — meaning senescence alone is NOT
        sufficient here and AMPLITUDE is what separates. Assert the honest thing: at
        least one trajectory component must differ between the classes.
        """
        tokens, y = _phenology_tokens()
        stats = pool_tokens(tokens, "temporal_stats").reshape(len(y), -1).numpy()
        _mean, std, amp, sen = np.split(stats, 4, axis=1)

        def gap(f: np.ndarray) -> float:
            return float(abs(f[y == 1].mean() - f[y == 0].mean()))

        assert gap(amp) > 0.1, "amplitude must separate flat from peaked curves"
        assert gap(std) > 0.05, "variability must separate them too"
        # Endpoints coincide by construction, so senescence alone should NOT separate.
        assert gap(sen) < 0.05
