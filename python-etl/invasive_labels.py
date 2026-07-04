"""Invasive-species labels for riparian health (tamarisk / Russian olive).

Woody invasives are the dominant riparian degradation driver in the San Juan
Basin — tamarisk (saltcedar, *Tamarix*) and Russian olive (*Elaeagnus
angustifolia*). This module turns NMRipMap's vegetation classification into
invasive-vs-native training labels, so a classifier on the multi-temporal
features can map invasive cover *within the Stage-1 riparian extent*. Invasive
dominance is a negative health signal (poor native habitat, altered hydrology,
fire risk).

Label source: NMRipMap `L3_Name` / NVC fields tag invasive stands (e.g.
"Lowland Native-Introduced Tamarisk Deciduous Riparian Forest", "Russian
Olive-Tamarisk Introduced Riparian Woodland and Scrub", NVC "Interior West
Ruderal Riparian Forest & Scrub"). NM-only — the classifier trains/validates on
NM and extrapolates to CO. Binary invasive-vs-native to start (species split is
a stretch). See docs/specs/2026-07-04-stage3-annual-change.md (invasives).
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

logger = logging.getLogger(__name__)

NMRIPMAP_SANJUAN_QUERY = (
    "https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/"
    "NM_RipMap_2_0_Plus_All_Levels/MapServer/13/query"
)
# Substrings (lowercased) that mark an NMRipMap stand as invasive-present.
INVASIVE_KEYWORDS = (
    "tamarix", "tamarisk", "saltcedar", "russian olive", "elaeagnus",
    "introduced", "ruderal",
)

LABEL_NATIVE = 0
LABEL_INVASIVE = 1
LABEL_NODATA = -1
_DEG_PER_M = 1.0 / 111_320.0


@dataclass(frozen=True)
class InvasiveLabelGrid:
    """Invasive/native label grid aligned to a bbox.

    Attributes:
        label: ``(H, W)`` int8 — 1 invasive-present, 0 native riparian, -1 no data.
        n_invasive_polys: Count of invasive-flagged NMRipMap polygons.
        n_native_polys: Count of native-riparian polygons.
    """

    label: np.ndarray
    n_invasive_polys: int
    n_native_polys: int


def is_invasive(l3_name: str | None, nvc_group: str | None) -> bool:
    """True if an NMRipMap vegetation class indicates invasive presence."""
    text = f"{l3_name or ''} {nvc_group or ''}".lower()
    return any(kw in text for kw in INVASIVE_KEYWORDS)


def fetch_nmripmap_veg(
    bbox: tuple[float, float, float, float], page: int = 400, timeout: int = 60,
) -> list[dict]:
    """Fetch NMRipMap polygons with vegetation-class attributes for a bbox.

    Returns:
        List of dicts with ``geom`` (shapely), ``l3_name``, ``nvc_group``.
    """
    env = {
        "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
        "spatialReference": {"wkid": 4326},
    }
    out: list[dict] = []
    offset = 0
    while True:
        params = {
            "geometry": json.dumps(env), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "where": "1=1", "outFields": "L3_Name,NVC_Group",
            "returnGeometry": "true", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page,
        }
        feats = requests.get(NMRIPMAP_SANJUAN_QUERY, params=params, timeout=timeout).json().get(
            "features", [])
        if not feats:
            break
        for f in feats:
            g = f.get("geometry")
            if not g:
                continue
            props = f.get("properties", {})
            out.append({
                "geom": shapely_shape(g),
                "l3_name": props.get("L3_Name"),
                "nvc_group": props.get("NVC_Group"),
            })
        if len(feats) < page:
            break
        offset += page
    logger.info("NMRipMap veg: fetched %d polygons for %s", len(out), bbox)
    return out


def grid_shape(bbox: tuple[float, float, float, float], resolution_m: float) -> tuple[int, int]:
    """Compute ``(height, width)`` for a bbox at a metre resolution."""
    deg = resolution_m * _DEG_PER_M
    return (max(1, round((bbox[3] - bbox[1]) / deg)),
            max(1, round((bbox[2] - bbox[0]) / deg)))


def build_invasive_labels(
    bbox: tuple[float, float, float, float],
    shape: tuple[int, int],
    transform=None,
) -> InvasiveLabelGrid:
    """Fetch NMRipMap and rasterize an invasive/native label grid.

    Native riparian is burned first, invasive on top (invasive wins on overlap),
    so mixed "Native-Introduced" stands count as invasive-present.

    Args:
        bbox: AOI ``(minx, miny, maxx, maxy)`` in EPSG:4326/4269.
        shape: ``(H, W)`` grid to rasterize onto (align to the feature grid).
        transform: Affine transform of the target grid. Defaults to a bbox-fit
            transform; pass the feature cube's geobox affine for exact alignment.

    Returns:
        An :class:`InvasiveLabelGrid`.
    """
    polys = fetch_nmripmap_veg(bbox)
    h, w = shape
    if transform is None:
        transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], w, h)

    invasive = [p["geom"] for p in polys if is_invasive(p["l3_name"], p["nvc_group"])]
    native = [p["geom"] for p in polys if not is_invasive(p["l3_name"], p["nvc_group"])]

    label = np.full(shape, LABEL_NODATA, dtype=np.int8)
    if native:
        native_mask = rasterize(
            ((g, 1) for g in native), out_shape=shape, transform=transform,
            fill=0, dtype="uint8",
        ).astype(bool)
        label[native_mask] = LABEL_NATIVE
    if invasive:
        invasive_mask = rasterize(
            ((g, 1) for g in invasive), out_shape=shape, transform=transform,
            fill=0, dtype="uint8",
        ).astype(bool)
        label[invasive_mask] = LABEL_INVASIVE

    logger.info(
        "Invasive labels: %d invasive-px, %d native-px (%d invasive / %d native polys)",
        int((label == LABEL_INVASIVE).sum()), int((label == LABEL_NATIVE).sum()),
        len(invasive), len(native),
    )
    return InvasiveLabelGrid(
        label=label, n_invasive_polys=len(invasive), n_native_polys=len(native),
    )
