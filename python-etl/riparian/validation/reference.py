"""Reference-layer validation for riparian delineation.

Validates the Stage-1 delineation against an *independent* mapped-riparian
reference rather than only weak-label holdouts. For the New Mexico portion of
the San Juan basin the reference is NMRipMap v2.0 Plus (Natural Heritage New
Mexico), a fine-scale riparian vegetation map — queried live from its ArcGIS
MapServer.

Both the reference polygons and our predicted extent are rasterized onto a
common grid, then compared pixel-wise (IoU / precision / recall / F1). This is
the metric that turns "spatial-CV against noisy weak labels" into "agreement
with an authoritative map". Validate NM (NMRipMap) and CO (CO-RIP) separately —
their methodologies differ. See
docs/specs/2026-07-03-stage1-riparian-delineation.md (reference layers).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import numpy as np
import requests
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import shape as shapely_shape
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# NMRipMap Gila Region San Juan, Level 1 (the base mapped-riparian polygons).
NMRIPMAP_SANJUAN_QUERY = (
    "https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/"
    "NM_RipMap_2_0_Plus_All_Levels/MapServer/13/query"
)
RESOLUTION_M = 20.0
_DEG_PER_M = 1.0 / 111_320.0


@dataclass(frozen=True)
class ValidationReport:
    """Pixel-wise agreement between predicted extent and a reference layer.

    Attributes:
        reference: Reference name (e.g. ``'NMRipMap'``).
        iou: Intersection-over-union of the two riparian masks.
        precision: TP / (TP + FP) — of predicted riparian, how much is reference.
        recall: TP / (TP + FN) — of reference riparian, how much we found.
        f1: Harmonic mean of precision and recall.
        pred_px: Predicted riparian pixels.
        reference_px: Reference riparian pixels.
        grid: ``(height, width)`` of the comparison grid.
    """

    reference: str
    iou: float
    precision: float
    recall: float
    f1: float
    pred_px: int
    reference_px: int
    grid: tuple[int, int]


# ---------------------------------------------------------------------------
# Reference fetch (ArcGIS REST, paginated)
# ---------------------------------------------------------------------------


def fetch_nmripmap(
    bbox: tuple[float, float, float, float],
    page: int = 500,
    timeout: int = 60,
    woody_only: bool = True,
) -> list:
    """Fetch NMRipMap San Juan **woody riparian** polygons intersecting a bbox.

    .. warning::
       This function previously returned *every* polygon on the assumption that
       "all returned polygons are riparian". **That was false.** NMRipMap classifies
       its mapping units (``L1_Code``/``L2_Code``): of ~10,300 polygons in the San Juan
       AOI only ~5,700 are woody riparian — the rest include 1,271 Urban, 781
       Agriculture, 351 Water/Channel and 283 Roads. Rasterizing them all as
       ``riparian = 1`` taught the model *corridor membership* rather than riparian
       vegetation, and taught agriculture — the class the weak labels already failed
       on — as positive.

    It now filters to the woody riparian classes (``IA``, ``IB``, ``IC``, ``IE``,
    ``IIA``, ``IIB``), matching the project's own definition in ``weak_labels.py``
    ("riparian is woody vegetation (tree/shrub) growing near water, not wetland").

    For multi-class labels (water / agriculture / other), or the tamarisk-vs-native
    split, use :mod:`riparian.labels.nmripmap` directly.

    Args:
        bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4326/4269 (treated as WGS84).
        page: Records per request.
        timeout: Per-request timeout (seconds).
        woody_only: Keep only woody riparian classes. Set False to get every mapped
            polygon (the old, incorrect behaviour) — only for corridor-extent analysis.

    Returns:
        List of shapely geometries (EPSG:4326).
    """
    from riparian.labels.nmripmap import fetch_labeled, woody_riparian

    polys = fetch_labeled(bbox, page=page, timeout=timeout)
    if woody_only:
        return woody_riparian(polys)
    return [p.geometry for p in polys]


def _fetch_nmripmap_unfiltered(
    bbox: tuple[float, float, float, float], page: int = 500, timeout: int = 60,
) -> list:
    """Original unfiltered fetch — retained only for the corridor-extent comparison."""
    env = {
        "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
        "spatialReference": {"wkid": 4326},
    }
    geoms: list = []
    offset = 0
    while True:
        params = {
            "geometry": json.dumps(env), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "where": "1=1", "returnGeometry": "true", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page,
        }
        resp = requests.get(NMRIPMAP_SANJUAN_QUERY, params=params, timeout=timeout)
        feats = resp.json().get("features", [])
        if not feats:
            break
        geoms.extend(
            shapely_shape(f["geometry"]) for f in feats if f.get("geometry")
        )
        if len(feats) < page:
            break
        offset += page
    logger.info("NMRipMap: fetched %d riparian polygons for %s", len(geoms), bbox)
    return geoms


# ---------------------------------------------------------------------------
# Rasterize + compare (pure)
# ---------------------------------------------------------------------------


def grid_shape(bbox: tuple[float, float, float, float], resolution_m: float) -> tuple[int, int]:
    """Compute ``(height, width)`` for a bbox at a metre resolution."""
    deg = resolution_m * _DEG_PER_M
    width = max(1, round((bbox[2] - bbox[0]) / deg))
    height = max(1, round((bbox[3] - bbox[1]) / deg))
    return (height, width)


def rasterize_mask(
    geoms: list, bbox: tuple[float, float, float, float], shape: tuple[int, int],
) -> np.ndarray:
    """Rasterize polygons to a boolean mask on the bbox grid."""
    if not geoms:
        return np.zeros(shape, dtype=bool)
    h, w = shape
    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], w, h)
    burned = rasterize(
        ((g, 1) for g in geoms), out_shape=shape, transform=transform,
        fill=0, dtype="uint8",
    )
    return burned.astype(bool)


def compare_masks(
    reference: np.ndarray, prediction: np.ndarray, name: str,
) -> ValidationReport:
    """Compute IoU / precision / recall / F1 between two riparian masks."""
    inter = int((reference & prediction).sum())
    union = int((reference | prediction).sum())
    tp = inter
    fp = int((prediction & ~reference).sum())
    fn = int((reference & ~prediction).sum())
    iou = inter / union if union else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return ValidationReport(
        reference=name, iou=iou, precision=precision, recall=recall, f1=f1,
        pred_px=int(prediction.sum()), reference_px=int(reference.sum()),
        grid=reference.shape,
    )


# ---------------------------------------------------------------------------
# Prediction fetch
# ---------------------------------------------------------------------------


def load_prediction_geoms(engine: Engine, huc12: str, method: str = "rf") -> list:
    """Load predicted riparian polygons for a tile from silver.riparian_extent.

    Uses parameterized SQLAlchemy + WKB → shapely (avoids a geopandas/pandas
    ``read_postgis`` params quirk under pandas 3).
    """
    from shapely import wkb

    sql = text(
        "SELECT ST_AsBinary(geom) AS wkb FROM silver.riparian_extent "
        "WHERE huc12 = :huc12 AND method = :method"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"huc12": huc12, "method": method}).fetchall()
    return [wkb.loads(bytes(r[0])) for r in rows if r[0] is not None]


def validate_against_nmripmap(
    engine: Engine,
    huc12: str,
    bbox: tuple[float, float, float, float],
    *,
    method: str = "rf",
    resolution_m: float = RESOLUTION_M,
) -> ValidationReport:
    """Validate a tile's predicted extent against NMRipMap (NM reference).

    Args:
        engine: SQLAlchemy engine.
        huc12: Tile id whose prediction to validate.
        bbox: Tile ``(minx, miny, maxx, maxy)`` in EPSG:4269.
        method: Prediction method to validate (``'rf'`` | ``'olmoearth'``).
        resolution_m: Comparison-grid pixel size.

    Returns:
        A :class:`ValidationReport`.
    """
    shape = grid_shape(bbox, resolution_m)
    ref_geoms = fetch_nmripmap(bbox)
    pred_geoms = load_prediction_geoms(engine, huc12, method)
    reference = rasterize_mask(ref_geoms, bbox, shape)
    prediction = rasterize_mask(pred_geoms, bbox, shape)
    report = compare_masks(reference, prediction, "NMRipMap")
    logger.info(
        "NMRipMap validation (%s): IoU=%.3f precision=%.3f recall=%.3f f1=%.3f "
        "(pred %d px, ref %d px, grid %s)",
        huc12, report.iou, report.precision, report.recall, report.f1,
        report.pred_px, report.reference_px, report.grid,
    )
    return report
