"""Baseline riparian delineation model (Stage 1b).

RandomForest on the multitemporal feature stack — the label-efficient,
literature-standard baseline the OlmoEarth foundation model is measured
against. scikit-learn's RandomForest is the default (CPU-only, no OpenMP);
XGBoost is an optional drop-in when ``libomp`` is available.

Trains on weak labels (LANDFIRE ∧ NLCD ∧ NWI agreement) and predicts a
per-pixel riparian probability. See
docs/specs/2026-07-03-stage1-riparian-delineation.md and
docs/decisions/2026-07-03-delineation-over-hydrology-buffers.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier

logger = logging.getLogger(__name__)

METHOD = "rf"  # matches silver.riparian_extent.method CHECK constraint
DEFAULT_MODEL_VERSION = "rf-v1"


@dataclass(frozen=True)
class DelineationModel:
    """A trained delineation classifier plus the metadata to reproduce it.

    Attributes:
        classifier: Fitted scikit-learn estimator with ``predict_proba``.
        feature_names: Feature column order the model expects.
        method: Method tag written to ``silver.riparian_extent`` (``'rf'``).
        model_version: Version string written alongside predictions.
    """

    classifier: RandomForestClassifier
    feature_names: tuple[str, ...]
    method: str = METHOD
    model_version: str = DEFAULT_MODEL_VERSION


def train(
    features: np.ndarray,
    labels: np.ndarray,
    feature_names: tuple[str, ...],
    *,
    n_estimators: int = 300,
    max_depth: int | None = None,
    random_state: int = 42,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> DelineationModel:
    """Fit a RandomForest riparian classifier on weak-labeled samples.

    Args:
        features: ``(n_samples, n_features)`` matrix.
        labels: ``(n_samples,)`` boolean/int riparian labels.
        feature_names: Column names aligned with ``features``.
        n_estimators: Number of trees.
        max_depth: Tree depth cap (None = grow until pure).
        random_state: Seed for reproducibility.
        model_version: Version string stored on the model.

    Returns:
        A fitted :class:`DelineationModel`.

    Raises:
        ValueError: If shapes are inconsistent or a class is missing.
    """
    if features.ndim != 2:
        raise ValueError(f"features must be 2-D, got shape {features.shape}")
    if features.shape[0] != labels.shape[0]:
        raise ValueError("features and labels must have the same n_samples")
    if features.shape[1] != len(feature_names):
        raise ValueError("feature_names length must match features columns")
    if len(np.unique(labels)) < 2:
        raise ValueError("labels must contain both riparian and non-riparian")

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        class_weight="balanced",  # riparian is the minority class
        n_jobs=-1,
    )
    clf.fit(features, labels.astype(int))
    logger.info(
        "Trained RF: %d samples, %d features, %d trees",
        features.shape[0], features.shape[1], n_estimators,
    )
    return DelineationModel(
        classifier=clf,
        feature_names=tuple(feature_names),
        model_version=model_version,
    )


def predict_proba(model: DelineationModel, features: np.ndarray) -> np.ndarray:
    """Predict per-sample riparian probability in [0, 1].

    Args:
        model: A trained :class:`DelineationModel`.
        features: ``(n_samples, n_features)`` matrix (same column order).

    Returns:
        ``(n_samples,)`` array of P(riparian).
    """
    if features.shape[1] != len(model.feature_names):
        raise ValueError("feature count does not match the trained model")
    classes = list(model.classifier.classes_)
    pos_col = classes.index(1) if 1 in classes else len(classes) - 1
    return model.classifier.predict_proba(features)[:, pos_col]


def feature_importance(model: DelineationModel) -> dict[str, float]:
    """Return feature importances as a name → importance dict (descending)."""
    pairs = zip(model.feature_names, model.classifier.feature_importances_)
    return dict(sorted(pairs, key=lambda kv: kv[1], reverse=True))
