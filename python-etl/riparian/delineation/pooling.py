"""Temporal pooling of OlmoEarth encoder tokens — the choice that IS the experiment.

Deliberately free of any `olmoearth_pretrain_minimal` import. This is pure tensor algebra;
tying it to the model package would mean the pooling logic could only be tested wherever the
(heavy, CUDA-adjacent) foundation-model wheel is installed — which is exactly the place CI
isn't. Keeping it standalone lets `tests/test_olmoearth_pooling.py` run on plain CPU torch,
so the phenology-preservation proof is verified on every push rather than only on a laptop.

`riparian.delineation.olmoearth` re-exports these names, so existing imports keep working.
"""

from __future__ import annotations

from typing import Final

import torch

# The encoder returns tokens of shape (B, P_H, P_W, T, Band_Sets, D). Something has to collapse
# that to one feature vector per patch before a classifier head sees it, and THAT CHOICE IS THE
# EXPERIMENT.
#
# `mean_time` averages over T. For semi-arid riparian delineation that is not a neutral default
# — it is destructive. Riparian phreatophytes are identified by *staying green into the dry
# season* (their roots reach groundwater) while the uplands around them brown out. That signal
# lives entirely in how a pixel's spectrum CHANGES across the season. Average the time axis away
# and a riparian patch and an irrigated-alfalfa patch with the same seasonal mean become the same
# vector.
#
# `mean_time` is retained so the ablation is a controlled A/B against the published number, not a
# silent fix. See docs/olmoearth-vs-rf-baseline.md — where the honest finding is that this defect
# is real but explains only a small part of the RF-vs-FM gap.
POOLINGS: Final[tuple[str, ...]] = ("mean_time", "temporal_stats", "concat_time")
DEFAULT_POOLING: Final[str] = "temporal_stats"

# Hard ceiling: the encoder's temporal embedding table has exactly this many entries. Handing it
# more timesteps fails deep inside einops ("Shape mismatch, 12 != 18"), not at our boundary — so
# we validate against it. It is also exactly the depth Ai2's mangrove recipe uses (12 monthly
# mosaics), which is not a coincidence.
MAX_MODEL_TIMESTEPS: Final[int] = 12


def pool_tokens(tokens: torch.Tensor, pooling: str = DEFAULT_POOLING) -> torch.Tensor:
    """Collapse encoder tokens ``(B, P_H, P_W, T, Band_Sets, D)`` to ``(B, P_H, P_W, F)``.

    The band-set axis is always averaged (it is a spectral-resolution grouping, not a signal we
    can order — and it is 3 on OlmoEarth v1 but 1 on v1.1, which merges the S2 bands into single
    tokens, so this must not be assumed). The TIME axis is the one under test.

    Poolings:
        ``mean_time``: mean over T. The original behaviour — **destroys phenology**. Retained so
            the ablation is a controlled comparison.
        ``temporal_stats``: mean, std, and the two order-dependent contrasts that carry phenology
            — amplitude (max−min) and senescence (late minus early). The cheap, RF-head-compatible
            way to keep the seasonal trajectory. ``F = 4*D``.
        ``concat_time``: the full trajectory, ``F = T*D``. Most faithful, widest features.

    Args:
        tokens: Encoder output ``(B, P_H, P_W, T, Band_Sets, D)``.
        pooling: One of :data:`POOLINGS`.

    Returns:
        ``(B, P_H, P_W, F)`` float tensor.

    Raises:
        ValueError: If ``pooling`` is unknown, or a trajectory pooling is requested with fewer
            than 2 timesteps (there is no trajectory to describe).
    """
    if pooling not in POOLINGS:
        raise ValueError(f"pooling must be one of {POOLINGS}, got {pooling!r}")

    per_t = tokens.mean(dim=4)                       # (B, P_H, P_W, T, D) — band-sets only
    n_t = per_t.shape[3]

    if pooling == "mean_time":
        return per_t.mean(dim=3)                     # (B, P_H, P_W, D)

    if n_t < 2:
        raise ValueError(
            f"pooling={pooling!r} needs >=2 timesteps to describe a trajectory, got {n_t}. "
            "Widen date_range / raise max_timesteps, or use 'mean_time'."
        )

    if pooling == "concat_time":
        b, ph, pw, t, d = per_t.shape
        return per_t.reshape(b, ph, pw, t * d)       # (B, P_H, P_W, T*D)

    # temporal_stats — cheap, fixed-width, and keeps the seasonal trajectory.
    # `per_t` is time-ordered (build_sentinel2_cube sorts by time), so `senescence` is a real
    # early->late contrast, not an arbitrary difference between two unordered slices.
    mean = per_t.mean(dim=3)
    std = per_t.std(dim=3)
    amplitude = per_t.amax(dim=3) - per_t.amin(dim=3)
    senescence = per_t[:, :, :, -1, :] - per_t[:, :, :, 0, :]
    return torch.cat([mean, std, amplitude, senescence], dim=-1)   # (B, P_H, P_W, 4*D)
