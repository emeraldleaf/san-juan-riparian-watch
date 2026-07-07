"""Stage 1 delineation orchestrator.

Ties the verified pieces into one run: STAC datacube → features → STAC weak
labels → train (RF baseline) → spatial-CV → predict → vectorize → write
``silver.riparian_extent``. Also persists the weak-labeled samples to
``bronze.riparian_training_samples`` for reproducibility.

Invoked from entrypoint.py as ``--mode delineate``. See
docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np
from rasterio.features import shapes as raster_shapes
from rasterio.transform import Affine, from_bounds
from scipy import ndimage
from shapely.geometry import shape as shapely_shape
from sklearn.ensemble import RandomForestClassifier
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from riparian.delineation.baseline import (
    DEFAULT_MODEL_VERSION,
    DelineationModel,
    predict_proba,
    train,
)
from riparian.delineation.validate import CvReport, assign_spatial_folds, spatial_cv
from riparian.datacube.features import FeatureStack, build_feature_stack
from riparian.delineation.hand import build_hand_envelope
from riparian.datacube.stac import (
    CubeRequest,
    PlanetaryComputerSearcher,
    StacSearcher,
    build_landcover_grid,
    build_sentinel2_cube,
)
from riparian.delineation.weak_labels import (
    LabelGrid,
    PostGISWeakLabelWriter,
    build_weak_label_grid,
    grid_to_samples,
    labels_for_pixels,
    load_nwi_mask,
)
from riparian.validation.reference import fetch_nmripmap, rasterize_mask

logger = logging.getLogger(__name__)

DEFAULT_RESOLUTION_M = 10.0
# Operating point chosen from a threshold sweep validated against NMRipMap on the
# Malpais tile: 0.30 gives F1 0.64 / IoU 0.47 / recall 0.50 at 0.90 precision, vs
# 0.51 / 0.34 / 0.35 at 0.94 precision for the old 0.5 default. See
# docs/specs/2026-07-03-stage1-riparian-delineation.md (reference validation).
PROBABILITY_THRESHOLD = 0.30

# Post-processing: drop speck regions below this area (per-pixel salt-and-pepper
# that adds noise + payload without signal) and simplify the raster→vector
# staircase edges — so the stored extent is clean + light by construction.
MIN_MAPPING_UNIT_M2 = 500.0
_DEG_PER_M = 1.0 / 111_320.0


@dataclass(frozen=True)
class DelineationResult:
    """Outcome of a delineation run.

    Attributes:
        method: ``'rf'`` or ``'olmoearth'``.
        model_version: Version tag written to the DB.
        n_training: Labeled training pixels used.
        cv: Spatial cross-validation report (the honest generalisation estimate).
        n_polygons: Riparian polygons written to silver.riparian_extent.
    """

    method: str
    model_version: str
    n_training: int
    cv: CvReport
    n_polygons: int


def run_delineation(
    bbox: tuple[float, float, float, float],
    engine: Engine,
    *,
    date_range: str,
    huc12: str | None = None,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    max_cloud_cover: int = 30,
    searcher: StacSearcher | None = None,
    use_nwi: bool = True,
    use_hand_envelope: bool = True,
    persist_samples: bool = True,
    max_train_pixels: int = 50_000,
    probability_threshold: float = PROBABILITY_THRESHOLD,
    label_source: str = "weak",
) -> DelineationResult:
    """Run the RF-baseline delineation over an AOI and write results.

    Args:
        bbox: AOI ``(minx, miny, maxx, maxy)`` in EPSG:4269.
        engine: SQLAlchemy engine for writes.
        date_range: STAC datetime range for the Sentinel-2 stack.
        resolution_m: Grid pixel size in metres.
        max_cloud_cover: Cloud ceiling for scene selection.
        searcher: STAC searcher (defaults to Planetary Computer).
        use_nwi: Include NWI wetlands as a third weak-label vote.
        persist_samples: Write weak-labeled samples to bronze.

    Returns:
        A :class:`DelineationResult`.

    Raises:
        RuntimeError: If no imagery is found or the labels are single-class.
    """
    searcher = searcher or PlanetaryComputerSearcher()
    request = CubeRequest(
        bbox=bbox, date_range=date_range, resolution_m=resolution_m,
        max_cloud_cover=max_cloud_cover,
    )

    cube = build_sentinel2_cube(request, searcher)
    if cube is None:
        raise RuntimeError(f"No Sentinel-2 imagery for {bbox} over {date_range}")
    features = build_feature_stack(cube)

    # Stage 1A: HAND candidate-corridor envelope (constrains the riparian output).
    envelope: np.ndarray | None = None
    if use_hand_envelope:
        hand = build_hand_envelope(bbox, searcher, like=cube)
        if hand is not None and hand.envelope.shape == features.valid_mask.shape:
            envelope = hand.envelope
        elif hand is not None:
            logger.warning("HAND envelope shape mismatch — skipping the corridor constraint")

    landcover = build_landcover_grid(request, searcher, like=cube)
    if landcover is None:
        raise RuntimeError("No land-cover products available for weak labels")

    grid = build_weak_label_grid(landcover, resolution_m)
    if use_nwi:
        nwi_mask = load_nwi_mask(engine, grid, bbox)
        if nwi_mask is not None:
            grid = build_weak_label_grid(landcover, resolution_m, nwi_mask=nwi_mask)

    # Lever #4: train on the NMRipMap reference map (actual mapped riparian) rather
    # than the weak-label "woody-near-water" proxy. NM-only — CO tiles have no
    # coverage and must stay label_source='weak' (see _nmripmap_label_grid).
    if label_source == "nmripmap":
        grid = _nmripmap_label_grid(grid, bbox, features.valid_mask.shape)
    model_version = "rf-nmripmap-v1" if label_source == "nmripmap" else DEFAULT_MODEL_VERSION

    row_index, labels, latlon = labels_for_pixels(grid, features.valid_mask)
    if len(np.unique(labels)) < 2:
        raise RuntimeError("weak labels are single-class — widen the AOI")
    x_train = features.data[row_index]
    logger.info(
        "Delineation training set: %d pixels, %.1f%% riparian",
        len(labels), 100.0 * labels.mean(),
    )

    if persist_samples:
        _persist_samples(engine, grid, huc12)

    # Subsample for tractable per-tile compute (stratified — preserves the sparse
    # riparian class). Weak labels are noisy, so a capped sample loses little.
    x_fit, y_fit, latlon_fit = _subsample(x_train, labels, latlon, max_train_pixels)
    model = train(x_fit, y_fit, features.feature_names, n_estimators=150, model_version=model_version)
    blocks = assign_spatial_folds(latlon_fit[:, 0], latlon_fit[:, 1])
    cv = spatial_cv(x_fit, y_fit, blocks, estimator=_cv_estimator())

    n_polygons = _predict_and_write(
        engine, model, features, bbox, resolution_m, huc12, envelope,
        probability_threshold)

    return DelineationResult(
        method=model.method, model_version=model.model_version,
        n_training=len(labels), cv=cv, n_polygons=n_polygons,
    )


def _nmripmap_label_grid(
    grid: LabelGrid, bbox: tuple[float, float, float, float], shape: tuple[int, int],
) -> LabelGrid:
    """Replace weak labels with rasterized NMRipMap truth (NM reference map).

    NMRipMap maps riparian-habitat polygons for New Mexico; a pixel inside a
    polygon is riparian (1), everything else non-riparian (0), aligned to the
    feature grid. Raises if the AOI has no NMRipMap coverage (e.g. a Colorado
    tile) so the caller can fall back to ``label_source='weak'``.
    """
    geoms = fetch_nmripmap(bbox)
    ref_mask = rasterize_mask(geoms, bbox, shape)
    positives = int(ref_mask.sum())
    if positives == 0:
        raise RuntimeError(
            f"NMRipMap has no coverage for {bbox} (New Mexico only — Colorado tiles "
            "need CO-RIP); use label_source='weak'"
        )
    logger.info("NMRipMap labels: %d riparian / %d pixels", positives, ref_mask.size)
    return replace(grid, label=ref_mask.astype(np.int8))


def _subsample(
    x: np.ndarray, y: np.ndarray, latlon: np.ndarray, max_n: int, seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Stratified subsample to ~max_n rows, keeping the sparse riparian class.

    Riparian is the rare class, so all positives are kept (capped at half the
    budget to avoid over-weighting) and the remainder is filled with a random
    draw of negatives. Returns the arrays unchanged if already within budget.
    """
    n = len(y)
    if n <= max_n:
        return x, y, latlon
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    keep_pos = pos if len(pos) <= max_n // 2 else rng.choice(pos, max_n // 2, replace=False)
    n_neg = max_n - len(keep_pos)
    keep_neg = rng.choice(neg, min(n_neg, len(neg)), replace=False)
    idx = np.concatenate([keep_pos, keep_neg])
    rng.shuffle(idx)
    logger.info(
        "Subsampled training set: %d → %d (%d riparian)",
        n, len(idx), int(y[idx].sum()),
    )
    return x[idx], y[idx], latlon[idx]


def _cv_estimator() -> RandomForestClassifier:
    """Lighter RandomForest for the spatial-CV folds (per-tile compute budget)."""
    return RandomForestClassifier(
        n_estimators=120, class_weight="balanced", random_state=42, n_jobs=-1,
        min_samples_leaf=2, max_features="sqrt",
    )


def _persist_samples(engine: Engine, grid: LabelGrid, huc12: str | None) -> None:
    """Write weak-labeled samples to bronze (best-effort; logs on failure)."""
    try:
        writer = PostGISWeakLabelWriter(engine)
        n = writer.write_samples(grid_to_samples(grid), huc12=huc12)
        logger.info("Persisted %d weak-labeled samples to bronze", n)
    except (SQLAlchemyError, OSError) as exc:  # persistence is non-critical
        logger.warning("Could not persist training samples: %s", exc)


def _predict_and_write(
    engine: Engine,
    model: DelineationModel,
    features: FeatureStack,
    bbox: tuple[float, float, float, float],
    resolution_m: float,
    huc12: str | None,
    envelope: np.ndarray | None = None,
    probability_threshold: float = PROBABILITY_THRESHOLD,
) -> int:
    """Predict over all valid pixels, vectorize riparian regions, write to silver.

    When a HAND ``envelope`` is provided, riparian output is confined to the
    candidate corridor (Stage 1A) — upland pixels the model scored high are
    dropped, cutting false positives.
    """
    proba = predict_proba(model, features.data)  # over valid pixels
    height, width = features.valid_mask.shape

    prob_grid = np.zeros((height, width), dtype=np.float32)
    prob_grid[features.valid_mask] = proba
    riparian = (prob_grid >= probability_threshold) & features.valid_mask
    if envelope is not None:
        riparian &= envelope

    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], width, height)
    rows = _vectorize(riparian, prob_grid, transform, model, resolution_m, huc12)
    return _write_extent(engine, rows, model, huc12)


def _vectorize(
    riparian: np.ndarray,
    prob_grid: np.ndarray,
    transform: Affine,
    model: DelineationModel,
    resolution_m: float,
    huc12: str | None,
) -> list[dict]:
    """Vectorize connected riparian regions into polygon rows.

    Each polygon carries the mean predicted probability over *its own* pixels
    (per-region, so the value is meaningful for downstream filtering/diffing),
    computed from the labeled connected components.
    """
    labeled, _ = ndimage.label(riparian)
    rows: list[dict] = []
    for geom, region_id in raster_shapes(
        labeled.astype(np.int32), mask=riparian, transform=transform,
    ):
        region_mask = labeled == int(region_id)
        # Min-mapping-unit: skip speck regions below the area floor.
        if int(region_mask.sum()) * resolution_m ** 2 < MIN_MAPPING_UNIT_M2:
            continue
        mean_prob = round(float(prob_grid[region_mask].mean()), 4)
        # Simplify the raster staircase edges (~3/4-pixel tolerance, in degrees).
        poly = shapely_shape(geom).simplify(
            resolution_m * _DEG_PER_M * 0.75, preserve_topology=True
        )
        if poly.is_empty:
            continue
        rows.append({
            "method": model.method,
            "model_version": model.model_version,
            "is_riparian": True,
            "riparian_probability": mean_prob,
            "cell_size_m": round(resolution_m, 2),
            "huc12": huc12,
            "wkt": poly.wkt,
        })
    return rows


_INSERT_EXTENT = text("""
    INSERT INTO silver.riparian_extent
        (method, model_version, is_riparian, riparian_probability, cell_size_m, huc12, geom)
    VALUES
        (:method, :model_version, :is_riparian, :riparian_probability, :cell_size_m,
         :huc12, ST_SetSRID(ST_GeomFromText(:wkt), 4269))
""")

_DELETE_METHOD = text(
    "DELETE FROM silver.riparian_extent "
    "WHERE method = :method AND model_version = :model_version "
    "AND huc12 IS NOT DISTINCT FROM :huc12"
)


def _write_extent(
    engine: Engine, rows: list[dict], model: DelineationModel, huc12: str | None,
) -> int:
    """Replace this method+version+tile's rows in silver.riparian_extent."""
    if not rows:
        logger.warning("No riparian polygons to write")
        return 0
    with engine.connect() as conn:
        conn.execute(_DELETE_METHOD, {
            "method": model.method, "model_version": model.model_version,
            "huc12": huc12,
        })
        conn.execute(_INSERT_EXTENT, rows)
        conn.commit()
    logger.info("Wrote %d riparian polygons to silver.riparian_extent", len(rows))
    return len(rows)
