"""Cluster-aware reach-block bootstrap CI for the FM-vs-RF LORO comparison.

The deploy-decision contract (spec #70) requires the macro-mean FM-minus-RF difference
to clear +0.04 with a **reach-block bootstrap CI above zero** before "GO" is formally
closed. Pixels within a reach are spatially correlated, so resampling pixels would fake
a huge sample; the honest unit of resampling is the **reach**. This module computes that
interval from the per-fold held-out AUROCs recorded in
``docs/2026-08-01-fm-vs-rf-loro-result.md``.

Run it::

    PYTHONPATH=python-etl python -m riparian.validation.reach_block_bootstrap

Statistical honesty, stated up front: with **n = 4 reaches** the bootstrap draws from a
tiny, lumpy distribution, so a wide interval is the expected outcome regardless of how
clean the point estimate looks. Reporting that wide interval *is* the result; the fix is
more reaches, not more resamples.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Per-fold held-out riparian AUROC (train on the other three, score the held-out reach
# once). Source of truth: the LORO result doc; reproduced locally 2026-08-21.
LORO_AUROC: dict[str, tuple[float, float]] = {
    # reach: (fm, rf)
    "malpais": (0.889, 0.557),
    "farmington": (0.892, 0.905),
    "kirtland": (0.812, 0.845),
    "aztec_animas": (0.894, 0.886),
}

#: The pre-registered macro-mean bar from the deploy-decision contract.
CONTRACT_MACRO_BAR: float = 0.04


@dataclass(frozen=True)
class BootstrapResult:
    """The reach-block bootstrap summary for the macro-mean FM-minus-RF difference."""

    point_estimate: float
    ci_low: float
    ci_high: float
    prob_positive: float
    n_reaches: int
    n_resamples: int

    @property
    def significant(self) -> bool:
        """True only if the 95% interval excludes zero from below."""
        return self.ci_low > 0.0


def reach_block_bootstrap(
    deltas: list[float],
    n_resamples: int = 100_000,
    seed: int = 20260822,
    alpha: float = 0.05,
) -> BootstrapResult:
    """Percentile bootstrap over reach-level paired differences.

    Args:
        deltas: One FM-minus-RF difference per reach (the cluster-level statistics).
        n_resamples: Bootstrap draws; excess draws cannot rescue a small ``deltas``.
        seed: Fixed so the reported interval is reproducible.
        alpha: Two-sided miscoverage; 0.05 gives the 95% interval.

    Returns:
        The point estimate, percentile CI, and the share of resample means above zero.

    Raises:
        ValueError: If fewer than two reach-level differences are supplied, if
            ``n_resamples`` is not positive, or if ``alpha`` is outside (0, 1).
    """
    if len(deltas) < 2:
        raise ValueError("reach-block bootstrap needs at least two reach deltas")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be positive, got {n_resamples}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(
        sum(rng.choice(deltas) for _ in range(n)) / n for _ in range(n_resamples)
    )
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    positive = sum(1 for m in means if m > 0) / n_resamples
    return BootstrapResult(
        point_estimate=sum(deltas) / n,
        ci_low=means[lo_idx],
        ci_high=means[hi_idx],
        prob_positive=positive,
        n_reaches=n,
        n_resamples=n_resamples,
    )


def main() -> None:
    """Compute and print the contract's significance check from the recorded AUROCs."""
    deltas = [fm - rf for fm, rf in LORO_AUROC.values()]
    result = reach_block_bootstrap(deltas)
    print("reach-block bootstrap, macro-mean FM-minus-RF (95% percentile CI)")
    for reach, (fm, rf) in LORO_AUROC.items():
        print(f"  {reach:<13} fm {fm:.3f}  rf {rf:.3f}  delta {fm - rf:+.3f}")
    print(
        f"  point estimate {result.point_estimate:+.3f} | "
        f"CI [{result.ci_low:+.3f}, {result.ci_high:+.3f}] | "
        f"P(mean > 0) = {result.prob_positive:.3f} | n = {result.n_reaches} reaches"
    )
    verdict = "SIGNIFICANT (CI > 0)" if result.significant else "NOT significant (CI includes 0)"
    print(f"  contract bar +{CONTRACT_MACRO_BAR:.2f}: point estimate "
          f"{'clears' if result.point_estimate >= CONTRACT_MACRO_BAR else 'misses'} it; {verdict}")


if __name__ == "__main__":
    main()
