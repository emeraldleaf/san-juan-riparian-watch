"""NMRipMap → normalized riparian label crosswalk.

NMRipMap polygons are **classified** — the layer carries an ``L1_Code``/``L2_Code``
hierarchy (plus NVC macrogroup/group/alliance, SWAP habitat, and quantitative cover
fields). The original ``validation.reference.fetch_nmripmap`` assumed *"all returned
polygons are riparian ... so no attribute filtering is needed"*. That is false, and it
is the single most damaging bug in the delineation track:

Of ~10,300 polygons in the San Juan AOI, only ~5,700 are woody riparian. The rest were
being trained as ``riparian = 1``, including **1,271 Urban**, **781 Agriculture**,
351 Water/Channel and 283 Roads. The model therefore learned *corridor membership*,
not riparian vegetation — and agriculture, the exact class the weak labels failed on
(~0.00 F1 on the Animas ag valley), was being taught as positive.

This module fetches NMRipMap **with its class attributes** and maps ``L2_Code`` to a
normalized label. The crosswalk is mirrored in ``crosswalk.csv`` for inspection.

Bonus: ``IC`` — *"Lowland Introduced Riparian Woodland and Scrub"* — is an authoritative
**tamarisk / Russian-olive** label (the Stage-2 invasive class), free ground truth that
the project otherwise lacks.

LABEL VINTAGE — 2020. READ THIS BEFORE PICKING A DATE RANGE.
    NMRipMap **v2.0 Plus** (Muldavin et al., 2023) was photo-interpreted from **NAIP 2020**
    (1 m ortho), per the service's own layer metadata. The labels therefore describe the
    corridor as it was in **2020**, not today.

    **Fit and validate against imagery from the same year.** The 2026-07-12 fair test used
    Sentinel-2 from *2024* against these 2020 labels — a 4-year gap over which corridors
    genuinely move (beetle defoliation, floods, channel migration, restoration), which fed
    every model label noise we introduced ourselves. It is worse for the invasive class than
    for extent: riparian *extent* is fairly stable over four years; *Tamarix cover* is exactly
    what the beetle has been changing since 2004.

    Predict any year you like — but fit on 2020.
    See docs/decisions/2026-07-12-olmoearth-finetune-invasives-with-extent-control.md.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Final

import requests
from shapely.geometry import shape as shapely_shape

logger = logging.getLogger(__name__)

# GRSJ Level-1 polygons (Gila Region / San Juan) — the classified riparian mapping units.
NMRIPMAP_SANJUAN_QUERY: Final[str] = (
    "https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/"
    "NM_RipMap_2_0_Plus_All_Levels/MapServer/13/query"
)

# --- normalized label vocabulary -------------------------------------------------

RIPARIAN_WOODY_NATIVE: Final[str] = "riparian_woody_native"
RIPARIAN_WOODY_INTRODUCED: Final[str] = "riparian_woody_introduced"  # tamarisk / Russian olive
RIPARIAN_HERBACEOUS: Final[str] = "riparian_herbaceous"
WATER: Final[str] = "water"
AGRICULTURE: Final[str] = "agriculture"
BARE_CHANNEL: Final[str] = "bare_channel_or_sandbar"
DEVELOPED: Final[str] = "developed"
UPLAND: Final[str] = "upland"
UNCERTAIN: Final[str] = "uncertain"
INVALID: Final[str] = "invalid"


@dataclass(frozen=True)
class LabelClass:
    """One row of the NMRipMap crosswalk."""

    l2_code: str
    source_name: str
    label: str
    confidence: float


# L2_Code -> normalized label. Verified against the live service (2026-07-11).
NMRIPMAP_L2_CROSSWALK: Final[dict[str, LabelClass]] = {
    c.l2_code: c
    for c in (
        # --- woody riparian (the target class) ---
        LabelClass("IA", "Montane Riparian Forest and Woodlands", RIPARIAN_WOODY_NATIVE, 0.95),
        LabelClass("IB", "Lowland Riparian Forest and Woodlands", RIPARIAN_WOODY_NATIVE, 0.95),
        LabelClass("IC", "Lowland Introduced Riparian Woodland and Scrub", RIPARIAN_WOODY_INTRODUCED, 0.90),
        LabelClass("IE", "Semi-Natural Riparian Woodland and Scrub", RIPARIAN_WOODY_NATIVE, 0.85),
        LabelClass("IIA", "Montane Riparian Shrubland", RIPARIAN_WOODY_NATIVE, 0.95),
        LabelClass("IIB", "Lowland Riparian Shrubland", RIPARIAN_WOODY_NATIVE, 0.95),
        # --- herbaceous riparian / wetland (riparian, but NOT woody) ---
        LabelClass("IIIA", "Montane Marshes and Wet Meadows", RIPARIAN_HERBACEOUS, 0.90),
        LabelClass("IIIB", "Lowland Marshes and Wet Meadows", RIPARIAN_HERBACEOUS, 0.90),
        LabelClass("IIIE", "Semi-natural Herbaceous Vegetation", UNCERTAIN, 0.40),
        # --- confusion + negative classes ---
        LabelClass("IVB", "Water/Channel", WATER, 0.95),
        LabelClass("IVD", "Agriculture", AGRICULTURE, 0.90),
        LabelClass("IVA", "Bare Unvegetated", BARE_CHANNEL, 0.70),
        LabelClass("IVE", "Urban/Built-Up Areas", DEVELOPED, 0.90),
        LabelClass("IVF", "Roads", DEVELOPED, 0.90),
        LabelClass("ID", "Upland Forest and Woodland", UPLAND, 0.90),
        LabelClass("IIC", "Upland Shrubland", UPLAND, 0.90),
        LabelClass("IIIC", "Montane Dry Meadow and Grassland", UPLAND, 0.85),
        LabelClass("IIID", "Lowland Dry Meadow and Grassland", UPLAND, 0.85),
        LabelClass("IIIF", "Upland Grassland", UPLAND, 0.90),
        LabelClass("IVG", "Upland Non-Veg", UPLAND, 0.90),
        # --- mapping artifact: must be masked out, never labelled "other" ---
        LabelClass("IVC", "Shadow", INVALID, 0.0),
    )
}

#: Woody riparian only — matches the project's own definition in ``weak_labels.py``
#: ("riparian is woody vegetation (tree/shrub) growing near water, not wetland").
WOODY_RIPARIAN_CODES: Final[frozenset[str]] = frozenset(
    {"IA", "IB", "IC", "IE", "IIA", "IIB"}
)

#: The introduced (tamarisk / Russian olive) subset — Stage-2 invasive ground truth.
INTRODUCED_WOODY_CODES: Final[frozenset[str]] = frozenset({"IC"})

# --- OlmoEarth Phase-1 target (segmentation classes; 0 = invalid/masked) ----------
#
# Agriculture gets its own class because it is THE spectral confusion class in the
# San Juan Basin — irrigated pasture looks like riparian in the growing season.
PHASE1_CLASS_IDS: Final[dict[str, int]] = {
    RIPARIAN_WOODY_NATIVE: 1,
    RIPARIAN_WOODY_INTRODUCED: 1,
    RIPARIAN_HERBACEOUS: 1,
    WATER: 2,
    AGRICULTURE: 3,
    BARE_CHANNEL: 4,
    DEVELOPED: 4,
    UPLAND: 4,
    UNCERTAIN: 0,
    INVALID: 0,
}

# --- Phase-2 target: split Tamarix out (the headline product feature) -------------
PHASE2_CLASS_IDS: Final[dict[str, int]] = {
    RIPARIAN_WOODY_INTRODUCED: 1,  # tamarisk / Russian olive
    RIPARIAN_WOODY_NATIVE: 2,
    RIPARIAN_HERBACEOUS: 3,
    WATER: 4,
    AGRICULTURE: 5,
    BARE_CHANNEL: 6,
    DEVELOPED: 6,
    UPLAND: 6,
    UNCERTAIN: 0,
    INVALID: 0,
}


@dataclass(frozen=True)
class LabeledPolygon:
    """An NMRipMap polygon with its normalized class."""

    geometry: object  # shapely geometry, EPSG:4326
    l2_code: str
    label: str
    confidence: float


def classify(l2_code: str | None) -> LabelClass | None:
    """Map an NMRipMap ``L2_Code`` to its normalized label.

    Args:
        l2_code: The polygon's ``L2_Code`` (e.g. ``"IB"``), or None.

    Returns:
        The matching :class:`LabelClass`, or None if the code is unknown/missing
        (unknown codes must be excluded, never silently treated as riparian).
    """
    if not l2_code:
        return None
    return NMRIPMAP_L2_CROSSWALK.get(l2_code.strip().upper())


#: Page size. Deliberately small: a 500-feature page is a 13-17 MB GeoJSON response and
#: the server intermittently fails on them (see :func:`_fetch_page`).
DEFAULT_PAGE: Final[int] = 200
_MAX_RETRIES: Final[int] = 4
_BACKOFF_BASE: Final[float] = 1.5


def fetch_labeled(
    bbox: tuple[float, float, float, float],
    page: int = DEFAULT_PAGE,
    timeout: int = 90,
) -> list[LabeledPolygon]:
    """Fetch NMRipMap polygons **with their class attributes** for a bbox.

    Unlike the original ``fetch_nmripmap``, this requests ``outFields`` and keeps the
    class, so callers can filter instead of treating every polygon as riparian.

    Pagination is fail-loud: a page that cannot be fetched raises rather than being
    treated as "no more data". Silently swallowing a failed middle page would drop
    hundreds of polygons and produce **gapped labels** — the same failure mode as the
    gapped-bronze bug in ``etl_pipeline._fetch_pages_parallel``.

    Args:
        bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4326.
        page: Records per request. Keep modest — responses are large.
        timeout: Per-request timeout in seconds.

    Returns:
        Labeled polygons. Unknown/``invalid`` classes are dropped.

    Raises:
        RuntimeError: If a page cannot be fetched after retries.
    """
    env = {
        "xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
        "spatialReference": {"wkid": 4326},
    }
    out: list[LabeledPolygon] = []
    offset = 0
    while True:
        feats = _fetch_page(env, offset, page, timeout)
        if not feats:
            break
        out.extend(_to_labeled(feats))
        if len(feats) < page:
            break
        offset += page

    _log_summary(out, bbox)
    return out


def _fetch_page(env: dict, offset: int, page: int, timeout: int) -> list[dict]:
    """Fetch one page, retrying transient failures.

    The service returns **HTTP 200 with an HTML error page** when it chokes on a large
    response — so a 200 is not proof of success and ``raise_for_status`` is not enough.
    Retry those, and raise if they persist; never return an empty page on failure.
    """
    params = {
        "geometry": json.dumps(env), "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "where": "1=1", "outFields": "L1_Code,L2_Code,L2_Name",
        "returnGeometry": "true", "f": "geojson",
        "resultOffset": offset, "resultRecordCount": page,
    }
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(NMRIPMAP_SANJUAN_QUERY, params=params, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()  # raises on the HTML error body
            if isinstance(payload, dict) and "error" in payload:
                raise ValueError(f"ArcGIS error body: {payload['error']}")
            return payload.get("features", [])
        except (ValueError, requests.RequestException) as exc:
            if attempt == _MAX_RETRIES - 1:
                raise RuntimeError(
                    f"NMRipMap page at offset={offset} failed after "
                    f"{_MAX_RETRIES} attempts — refusing to return gapped labels"
                ) from exc
            wait = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "NMRipMap offset=%d attempt %d/%d failed (%s) — retrying in %.1fs",
                offset, attempt + 1, _MAX_RETRIES, type(exc).__name__, wait,
            )
            time.sleep(wait)
    return []  # unreachable


def _to_labeled(feats: list[dict]) -> list[LabeledPolygon]:
    """Convert GeoJSON features to labeled polygons, dropping unknown/invalid classes."""
    out: list[LabeledPolygon] = []
    for f in feats:
        geom = f.get("geometry")
        if not geom:
            continue
        cls = classify((f.get("properties") or {}).get("L2_Code"))
        if cls is None or cls.label == INVALID:
            continue
        out.append(
            LabeledPolygon(shapely_shape(geom), cls.l2_code, cls.label, cls.confidence)
        )
    return out


def _log_summary(polys: list[LabeledPolygon], bbox: tuple) -> None:
    """Log the class breakdown so a bad crosswalk is visible, not silent."""
    counts: dict[str, int] = {}
    for p in polys:
        counts[p.label] = counts.get(p.label, 0) + 1
    logger.info(
        "NMRipMap %s: %d labeled polygons — %s",
        bbox, len(polys), ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    )


def woody_riparian(polys: list[LabeledPolygon]) -> list:
    """Geometries that are genuinely woody riparian (the delineation target)."""
    return [p.geometry for p in polys if p.l2_code in WOODY_RIPARIAN_CODES]


def introduced_woody(polys: list[LabeledPolygon]) -> list:
    """Geometries mapped as introduced woody riparian (tamarisk / Russian olive)."""
    return [p.geometry for p in polys if p.l2_code in INTRODUCED_WOODY_CODES]


def to_class_features(
    polys: list[LabeledPolygon], class_ids: dict[str, int] | None = None
) -> dict:
    """Build a GeoJSON FeatureCollection carrying integer class ids.

    This is the ``label`` vector layer consumed by the OlmoEarth scaffold
    (``olmoearth_run_data/riparian_extent/``), which rasterizes it to ``label_raster``.

    Args:
        polys: Labeled polygons from :func:`fetch_labeled`.
        class_ids: Label → class-id map. Defaults to :data:`PHASE1_CLASS_IDS`.

    Returns:
        A GeoJSON ``FeatureCollection``; class id 0 (invalid/uncertain) is dropped.
    """
    ids = class_ids or PHASE1_CLASS_IDS
    features = []
    for p in polys:
        cid = ids.get(p.label, 0)
        if cid == 0:
            continue
        features.append({
            "type": "Feature",
            "geometry": p.geometry.__geo_interface__,
            "properties": {
                "class": cid,
                "label": p.label,
                "l2_code": p.l2_code,
                "confidence": p.confidence,
            },
        })
    return {"type": "FeatureCollection", "features": features}
