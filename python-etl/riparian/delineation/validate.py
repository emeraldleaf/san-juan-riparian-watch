"""Spatial cross-validation for riparian delineation (Stage 1b).

Riparian training data is strongly spatially autocorrelated (neighbouring
pixels share phenology, terrain, and land use), so a random train/test split
leaks: a test pixel's neighbours are in the training set and accuracy is
inflated. This module blocks the study area into spatial tiles and holds out
whole tiles per fold (GroupKFold on tile id), which is the defensible way to
estimate how the model generalises to unseen ground.

Reports precision / recall / F1 / PR-AUC (average precision) / ROC-AUC averaged
across folds. See docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CvReport:
    """Cross-validated metrics, averaged over spatial folds.

    Attributes:
        n_folds: Number of spatial folds actually run.
        n_samples: Total labeled samples.
        metrics: Mean metric values (precision, recall, f1, pr_auc, roc_auc).
        per_fold: Per-fold metric dicts, in fold order.
    """

    n_folds: int
    n_samples: int
    metrics: dict[str, float]
    per_fold: list[dict[str, float]]


def assign_spatial_folds(
    lats: np.ndarray,
    lons: np.ndarray,
    block_deg: float = 0.02,
) -> np.ndarray:
    """Assign each sample a spatial-block id by binning its coordinates.

    Samples in the same ``block_deg × block_deg`` tile share a block id and are
    therefore never split across train/test. ~0.02 deg ≈ 2 km at mid-latitudes.

    Args:
        lats: ``(n_samples,)`` latitudes (EPSG:4269).
        lons: ``(n_samples,)`` longitudes.
        block_deg: Tile size in degrees.

    Returns:
        ``(n_samples,)`` integer block ids.
    """
    row = np.floor(lats / block_deg).astype(np.int64)
    col = np.floor(lons / block_deg).astype(np.int64)
    # Cantor-style pairing into a single id; exact value is irrelevant, only grouping.
    return row * 100_000 + col


def spatial_cv(
    features: np.ndarray,
    labels: np.ndarray,
    blocks: np.ndarray,
    *,
    n_folds: int = 5,
    estimator: RandomForestClassifier | None = None,
    threshold: float = 0.5,
) -> CvReport:
    """Run spatial (grouped) cross-validation and return averaged metrics.

    Whole spatial blocks are held out per fold. If there are fewer distinct
    blocks than ``n_folds``, the fold count is reduced to the block count.

    Args:
        features: ``(n_samples, n_features)`` matrix.
        labels: ``(n_samples,)`` boolean/int riparian labels.
        blocks: ``(n_samples,)`` spatial-block ids from :func:`assign_spatial_folds`.
        n_folds: Desired number of folds.
        estimator: Estimator to clone per fold (defaults to a balanced RF).
        threshold: Probability threshold for precision/recall/F1.

    Returns:
        A :class:`CvReport`.

    Raises:
        ValueError: If there are fewer than 2 spatial blocks (CV impossible).
    """
    y = labels.astype(int)
    n_blocks = len(np.unique(blocks))
    if n_blocks < 2:
        raise ValueError(
            f"spatial CV needs >=2 blocks, got {n_blocks} — widen the AOI or "
            "shrink block_deg"
        )
    folds = min(n_folds, n_blocks)
    if estimator is None:
        estimator = RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1,
        )

    gkf = GroupKFold(n_splits=folds)
    per_fold: list[dict[str, float]] = []
    for i, (tr, te) in enumerate(gkf.split(features, y, groups=blocks), start=1):
        if len(np.unique(y[tr])) < 2:
            logger.warning("Fold %d skipped: training split is single-class", i)
            continue
        model = clone(estimator)
        model.fit(features[tr], y[tr])
        proba = model.predict_proba(features[te])[:, list(model.classes_).index(1)]
        pred = (proba >= threshold).astype(int)
        fold_metrics = {
            "precision": float(precision_score(y[te], pred, zero_division=0)),
            "recall": float(recall_score(y[te], pred, zero_division=0)),
            "f1": float(f1_score(y[te], pred, zero_division=0)),
            "pr_auc": _safe_auc(average_precision_score, y[te], proba),
            "roc_auc": _safe_auc(roc_auc_score, y[te], proba),
        }
        per_fold.append(fold_metrics)
        logger.info("Fold %d/%d: %s", i, folds, _fmt(fold_metrics))

    if not per_fold:
        raise ValueError("no valid folds — every split was single-class")

    mean = {k: float(np.mean([f[k] for f in per_fold])) for k in per_fold[0]}
    logger.info("Spatial CV mean (%d folds): %s", len(per_fold), _fmt(mean))
    return CvReport(
        n_folds=len(per_fold),
        n_samples=int(features.shape[0]),
        metrics=mean,
        per_fold=per_fold,
    )


def _safe_auc(fn, y_true: np.ndarray, scores: np.ndarray) -> float:
    """Compute an AUC metric, returning NaN if the fold is single-class."""
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(fn(y_true, scores))


def _fmt(metrics: dict[str, float]) -> str:
    """Compact one-line metric formatting for logs."""
    return " ".join(f"{k}={v:.3f}" for k, v in metrics.items())
