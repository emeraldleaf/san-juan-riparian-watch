"""Validate the label layer **against the imagery**, before renting a GPU.

A label layer can be syntactically perfect — right CRS, right class ids, right schema — and still
be wrong in the only way that matters: it does not line up with the pixels. Nothing in
``rslearn`` will tell you. Training will run, the loss will fall, and the metrics will be
plausible-but-meaningless. You find out after you have paid for it.

So: check the labels against the imagery **first**. Three tests, cheapest first, each catching a
failure the previous one cannot see.

------------------------------------------------------------------------------------------------
1. SEPARABILITY — "do these labels describe anything the sensor can see?"
------------------------------------------------------------------------------------------------
Sample peak-growing-season (June–August) NDVI from Sentinel-2 **2020** — the label's own vintage —
inside every polygon, and ask how well NDVI alone separates riparian (class 1) from corridor
negatives (3/4).

Riparian vegetation in a semi-arid basin is, above all, *the green stuff by the river*. If NDVI
cannot separate the classes **at all**, the labels are not describing vegetation and no foundation
model will rescue them.

Read it as a floor, not a ceiling:

    AUC < 0.65   🔴 the labels are broken, or misaligned. STOP. Do not train.
    0.65 – 0.80  🟡 plausible. This is roughly what a semi-arid corridor should give — the
                 negatives are *supposed* to be hard, and irrigated agriculture (class 3) is
                 genuinely as green as riparian.
    AUC > 0.95   🟡 suspicious, not good. If one hand-computed index nearly solves the task, the
                 task is probably leaking — check that negatives are corridor negatives and not
                 desert.

------------------------------------------------------------------------------------------------
2. SHIFT — "are they aligned, or merely correlated?"
------------------------------------------------------------------------------------------------
The test that separability cannot do. Re-score separability with the labels translated by ±1, ±2,
±3 pixels, and find which offset scores best.

**If a shifted version beats the unshifted one, you have a registration bug** — the labels
correlate with the imagery (so test 1 passes) but sit systematically off it. A model trained on
that learns a blurred, displaced boundary, and every reported metric is quietly wrong.

This is the test I most want, because we have already been burned by its cousin: the AUC-0.23
incident *looked* exactly like a spatial misalignment and was in fact an unshuffled CV split. A
real misalignment would have looked identical. Guessing is not a method; measuring the offset is.

------------------------------------------------------------------------------------------------
3. EYES — "look at it."
------------------------------------------------------------------------------------------------
Write NAIP **2020** chips with the label polygons drawn on top, and *look at them*. NAIP 2020 at
0.6 m is the exact imagery NMRipMap was photo-interpreted from, so it is not a proxy for the
truth — it **is** the source the truth was drawn on.

No metric replaces this. A metric tells you the labels are self-consistent; only your eyes tell
you they are *on the trees*.

See CLAUDE.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import numpy as np

logger = logging.getLogger(__name__)

#: Fit against the label's own vintage. NMRipMap v2.0 Plus = NAIP 2020.
IMAGERY_YEAR: Final[int] = 2020

#: Peak growing season for the San Juan Basin — **the one definition**. Outside it, riparian NDVI
#: collapses toward upland and the whole test goes mute: a dormant reading is not a bare one.
#: Callers that score NDVI must filter to these months. `validate_materialized.py` imports this
#: rather than keeping its own copy — peak season defined twice is peak season that drifts, which is
#: how `num_classes` ended up wrong (see docs/method.md receipt 18).
PEAK_MONTHS: Final[frozenset[int]] = frozenset({6, 7, 8})

#: The same window as a STAC date range, derived so the two cannot disagree.
GROWING_SEASON: Final[str] = (
    f"{IMAGERY_YEAR}-{min(PEAK_MONTHS):02d}-01/{IMAGERY_YEAR}-{max(PEAK_MONTHS):02d}-31"
)

#: Below this, the labels are not describing anything the sensor can see. Hard stop.
MIN_SEPARABILITY_AUC: Final[float] = 0.65

#: Above this, suspect leakage rather than celebrate.
SUSPICIOUS_AUC: Final[float] = 0.95

#: Pixel offsets probed by the shift test (Sentinel-2 = 10 m/px).
SHIFTS: Final[tuple[int, ...]] = (-3, -2, -1, 0, 1, 2, 3)

POSITIVE_CLASS: Final[int] = 1

#: The hard negatives — the ones the model must learn to reject. Agriculture (3) is as green as
#: riparian; "other" (4) is the corridor's non-vegetated ground. **Water (2) is deliberately
#: excluded**: it is trivially separable from vegetation by NDVI, so letting it into the negative
#: set inflates every AUC and can clear the gate while agriculture stays inseparable. The
#: separability contract is riparian-vs-corridor, not riparian-vs-water.
CORRIDOR_NEGATIVE_CLASSES: Final[tuple[int, int]] = (3, 4)

#: A nonzero shift must beat zero by MORE than this to count as a real displacement. Sampling
#: jitter alone moves AUC by ~this much, so within it we call the labels aligned — and we snap the
#: reported best_shift to (0, 0) so the gate and the log cannot disagree.
ALIGNMENT_TOLERANCE: Final[float] = 0.01


def translate(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift ``mask`` by (dy, dx), filling vacated cells with 0 (no label) — **no wrap**.

    Public because it is part of the shift-test contract: the materialised validator
    (``validate_materialized.py``) shifts every window the same way and must translate identically.
    An underscore here would be a private symbol imported across the package boundary — a refactor
    of it would silently break the materialised gate.

    ``np.roll`` wraps edge pixels onto the opposite side, so a label touching the tile boundary
    would be scored against unrelated imagery on the far edge and could inflate the AUC. A padded
    translation drops what falls off the edge and leaves the newly exposed border unlabeled, which
    is what a real registration offset does.
    """
    out = np.zeros_like(mask)
    h, w = mask.shape
    if abs(dy) >= h or abs(dx) >= w:
        # The shift moves the whole array off-grid: nothing overlaps, so the result is all-zero
        # (all "no label"). Without this guard the slice bounds would cross and numpy would silently
        # write a mis-sized or empty region.
        return out
    src_y0, src_y1 = max(0, -dy), min(h, h - dy)
    src_x0, src_x1 = max(0, -dx), min(w, w - dx)
    dst_y0, dst_y1 = max(0, dy), min(h, h + dy)
    dst_x0, dst_x1 = max(0, dx), min(w, w + dx)
    out[dst_y0:dst_y1, dst_x0:dst_x1] = mask[src_y0:src_y1, src_x0:src_x1]
    return out


@dataclass(frozen=True)
class Separability:
    """How well NDVI alone separates riparian from corridor negatives."""

    auc: float
    n_positive: int
    n_negative: int
    median_ndvi_positive: float
    median_ndvi_negative: float

    @property
    def verdict(self) -> str:
        if self.auc < MIN_SEPARABILITY_AUC:
            return "BROKEN"
        if self.auc > SUSPICIOUS_AUC:
            return "SUSPICIOUS"
        return "OK"


@dataclass(frozen=True)
class Alignment:
    """The result of the shift test."""

    best_shift: tuple[int, int]
    best_auc: float
    unshifted_auc: float

    @property
    def is_aligned(self) -> bool:
        """True only when the reported best shift is exactly zero.

        The jitter tolerance is applied earlier, *inside best-shift selection* (see ``alignment``):
        a nonzero offset that beats zero by less than :data:`ALIGNMENT_TOLERANCE` is snapped back to
        ``(0, 0)`` there. So by the time we get here, a nonzero ``best_shift`` means a shift beat
        zero by a real margin — which must fail the gate. Keeping the tolerance out of this property
        is what stops the gate from passing while the log says "unshifted is best".
        """
        return self.best_shift == (0, 0)


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    """Rank-based AUC — the probability a random positive outranks a random negative.

    Computed from ranks rather than by sweeping thresholds: it is exact, needs no sklearn, and
    has no hidden shuffle to get wrong (see the AUC-0.23 incident).
    """
    pos = positive[np.isfinite(positive)]
    neg = negative[np.isfinite(negative)]
    if pos.size == 0 or neg.size == 0:
        raise ValueError("AUC needs both classes; one of them is empty after NaN removal")

    combined = np.concatenate([pos, neg])
    order = combined.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, combined.size + 1)

    # Average ranks within ties, or a constant band (e.g. a cloud-masked region) biases the result.
    _, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    sums = np.zeros(counts.size)
    np.add.at(sums, inverse, ranks)
    ranks = (sums / counts)[inverse]

    rank_sum = ranks[: pos.size].sum()
    return float((rank_sum - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def separability(ndvi_positive: np.ndarray, ndvi_negative: np.ndarray) -> Separability:
    """Test 1 — can NDVI see the classes at all?

    Args:
        ndvi_positive: NDVI values sampled inside riparian (class 1) polygons/pixels. NaNs allowed
            (cloud-masked); they are dropped before scoring.
        ndvi_negative: NDVI values sampled inside **corridor negatives** — agriculture (3) and other
            (4), *not* water (see :data:`CORRIDOR_NEGATIVE_CLASSES`). Passing water here inflates the
            AUC and defeats the point of the test.

    Returns:
        A :class:`Separability` with the AUC, per-class medians, finite-sample counts, and a verdict
        (BROKEN / OK / SUSPICIOUS). ``BROKEN`` (AUC < :data:`MIN_SEPARABILITY_AUC`) is a hard stop.
    """
    result = Separability(
        auc=auc(ndvi_positive, ndvi_negative),
        n_positive=int(np.isfinite(ndvi_positive).sum()),
        n_negative=int(np.isfinite(ndvi_negative).sum()),
        median_ndvi_positive=float(np.nanmedian(ndvi_positive)),
        median_ndvi_negative=float(np.nanmedian(ndvi_negative)),
    )
    logger.info(
        "separability: AUC=%.3f [%s] — riparian NDVI %.3f vs negative %.3f (n=%d/%d)",
        result.auc,
        result.verdict,
        result.median_ndvi_positive,
        result.median_ndvi_negative,
        result.n_positive,
        result.n_negative,
    )
    if result.verdict == "BROKEN":
        logger.error(
            "  🔴 NDVI cannot separate these labels. They are wrong or misaligned. DO NOT TRAIN."
        )
    elif result.verdict == "SUSPICIOUS":
        logger.warning(
            "  🟡 AUC > %.2f — one hand-computed index nearly solves the task. Suspect the "
            "negatives are desert, not corridor.",
            SUSPICIOUS_AUC,
        )
    return result


def best_shift(scores: dict[tuple[int, int], float]) -> tuple[int, int]:
    """The offset the shift test reports, given each candidate offset's AUC — **the one rule**.

    This is the gate's own pass/fail decision, so it is defined once and shared by both callers
    (``alignment`` here and the pooled ``validate_materialized``), rather than copied — two copies of
    a gate's decision rule are two rules free to drift.

    Two things happen:

    1. **Ties break toward the SMALLEST shift.** A corridor that runs straight for the length of the
       window is invariant under translation ALONG its own axis, so every offset on that axis scores
       identically. An arbitrary argmax there invents a displacement not in the data and reports a
       registration bug on perfectly aligned labels. Among equals, no shift wins.
    2. **The jitter tolerance is applied HERE, not in ``is_aligned``.** If the unshifted score is
       within :data:`ALIGNMENT_TOLERANCE` of the raw best, the "displacement" is sampling jitter, so
       we report ``(0, 0)``. This keeps ``best_shift``, ``is_aligned`` and the log message consistent
       — a nonzero result now always means a real, above-jitter offset that should fail the gate.

    Args:
        scores: Map from ``(dy, dx)`` offset to its AUC. Must contain ``(0, 0)``.

    Returns:
        The reported offset — ``(0, 0)`` when aligned or within jitter of the best.
    """
    raw_best = min(scores, key=lambda k: (-scores[k], abs(k[0]) + abs(k[1])))
    if scores[raw_best] - scores[(0, 0)] < ALIGNMENT_TOLERANCE:
        return (0, 0)
    return raw_best


def alignment(
    ndvi: np.ndarray,
    label_mask: np.ndarray,
    shifts: tuple[int, ...] = SHIFTS,
) -> Alignment:
    """Test 2 — the shift test. Does a translated label mask score BETTER?

    Args:
        ndvi: 2-D NDVI array (peak-season median), Sentinel-2 grid.
        label_mask: 2-D integer class array on the same grid. 0 = no label.
        shifts: Pixel offsets to probe, in both axes.

    Returns:
        The best-scoring offset. ``(0, 0)`` is what you want.
    """
    scores: dict[tuple[int, int], float] = {}
    for dy in shifts:
        for dx in shifts:
            shifted = translate(label_mask, dy, dx)
            pos = ndvi[shifted == POSITIVE_CLASS]
            neg = ndvi[np.isin(shifted, CORRIDOR_NEGATIVE_CLASSES)]
            if pos.size == 0 or neg.size == 0:
                continue
            scores[(dy, dx)] = auc(pos, neg)

    if (0, 0) not in scores:
        raise ValueError("the unshifted labels score nothing — the mask and NDVI grid disagree")

    best = best_shift(scores)
    result = Alignment(
        best_shift=best, best_auc=scores[best], unshifted_auc=scores[(0, 0)]
    )

    if result.is_aligned:
        logger.info(
            "alignment: ✓ unshifted is best (AUC=%.3f) — labels sit on the pixels",
            result.unshifted_auc,
        )
    else:
        dy, dx = result.best_shift
        logger.error(
            "alignment: 🔴 REGISTRATION BUG — shifting labels by (dy=%+d, dx=%+d) px raises AUC "
            "%.3f -> %.3f. The labels correlate with the imagery but do not sit ON it. "
            "Separability will still pass; every trained metric will be quietly wrong.",
            dy,
            dx,
            result.unshifted_auc,
            result.best_auc,
        )
    return result


def report(sep: Separability, align: Alignment) -> bool:
    """The Phase-0 gate: may we spend money on a GPU?

    Args:
        sep: Result of :func:`separability` (test 1). A ``BROKEN`` verdict fails the gate;
            ``SUSPICIOUS`` passes but is logged as a leakage warning upstream.
        align: Result of :func:`alignment` (test 2). Any nonzero ``best_shift`` fails the gate.

    Returns:
        ``True`` only if both tests pass — separability is not ``BROKEN`` **and** the labels are
        aligned. Deliberately a hard gate: every failure it catches is free here and expensive later.
    """
    ok = sep.verdict != "BROKEN" and align.is_aligned
    if ok:
        logger.info("✅ label layer validated against %d imagery — cleared for training", IMAGERY_YEAR)
    else:
        logger.error("❌ label layer FAILED validation — fix it before renting a GPU")
    return ok
