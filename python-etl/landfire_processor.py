"""LANDFIRE vegetation structure processor for riparian buffers.

Downloads LANDFIRE Existing Vegetation Type (EVT) and Existing
Vegetation Height (EVH) rasters from the USGS ArcGIS ImageServer,
clips to the watershed bounding box, and computes per-buffer
vegetation structure metrics using zonal statistics.

EVT provides species composition — useful for detecting native vs
non-native cover, shrub presence, and dominant lifeform.

EVH provides vertical complexity — vegetation height classes useful
for the SMP's vegetation structure scoring.

Uses the raster_processor framework for data fetching and masking.

Study area: San Juan Basin, HUC8 14080101.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import geopandas as gpd
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine

from raster_processor import (
    CategoricalStats,
    ContinuousStats,
    ImageServerSource,
    RasterSource,
    compute_categorical_zonal_stats,
    compute_continuous_zonal_stats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# LANDFIRE LF250 (latest version) ArcGIS ImageServer endpoints
LANDFIRE_EVT_URL = (
    "https://lfps.usgs.gov/arcgis/rest/services"
    "/Landfire_LF250/US_250EVT/ImageServer"
)
LANDFIRE_EVH_URL = (
    "https://lfps.usgs.gov/arcgis/rest/services"
    "/Landfire_LF250/US_250EVH/ImageServer"
)

# Simplified LANDFIRE EVT lifeform categories
# Full EVT has thousands of codes; we group by lifeform for the POC.
# These code ranges are from LANDFIRE documentation.
EVT_LIFEFORM_RANGES: list[tuple[range, str, str]] = [
    # (code range, lifeform category, description prefix)
    (range(2000, 3000), "Tree", "Forest/Woodland"),
    (range(3000, 4000), "Shrub", "Shrubland"),
    (range(4000, 5000), "Herb", "Herbaceous/Grassland"),
    (range(5000, 6000), "Sparse", "Sparsely Vegetated"),
    (range(7000, 8000), "Agriculture", "Agricultural"),
    (range(8000, 9000), "Developed", "Developed/Urban"),
    (range(9000, 10000), "Water/Barren", "Open Water/Barren"),
]

# Commonly observed riparian EVT codes for the San Juan Basin
# (subset of most relevant codes for interpretability)
EVT_NOTABLE_CODES: dict[int, str] = {
    2050: "Rocky Mountain Subalpine-Montane Riparian Woodland",
    2051: "Rocky Mountain Subalpine-Montane Riparian Shrubland",
    2155: "Rocky Mountain Lower Montane-Foothill Riparian Woodland",
    2156: "Rocky Mountain Lower Montane-Foothill Riparian Shrubland",
    2161: "Inter-Mountain Basins Greasewood Flat",
    2059: "Rocky Mountain Aspen Forest and Woodland",
    2025: "Rocky Mountain Montane Dry-Mesic Mixed Conifer Forest",
    2027: "Rocky Mountain Montane Mesic Mixed Conifer Forest",
    3028: "Rocky Mountain Lower Montane-Foothill Shrubland",
    3034: "Inter-Mountain Basins Big Sagebrush Shrubland",
    3036: "Colorado Plateau Mixed Low Sagebrush Shrubland",
    4010: "Western Great Plains Shortgrass Prairie",
    4065: "Rocky Mountain Subalpine-Montane Mesic Meadow",
    7011: "Pasture/Hay",
    7012: "Cultivated Cropland",
    8001: "Developed-Open Space",
    8002: "Developed-Low Intensity",
    8003: "Developed-Medium Intensity",
    8004: "Developed-High Intensity",
    9001: "Open Water",
    9003: "Barren",
}

# LANDFIRE EVH class codes → height ranges (meters)
# EVH is encoded as integers representing height class codes.
# The pixel values represent actual height in 10ths of meters for LF250.
# For LF250 EVH: pixel value = height in decimeters (1 = 0.1m)
# Values 101-999 represent actual heights; 0 and special codes are metadata.
EVH_NODATA_VALUES = frozenset({0, -9999, 32767})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BufferVegetation:
    """Vegetation structure entry for a single buffer from LANDFIRE.

    Attributes:
        buffer_id: Buffer primary key.
        evt_code: Dominant EVT code in this buffer.
        evt_name: EVT name or description.
        evh_class: EVH height class description.
        mean_height_m: Mean vegetation height in meters.
        dominant_lifeform: Dominant lifeform (Tree, Shrub, Herb, etc.).
        pixel_count: Number of raster pixels.
        area_pct: Percentage of buffer covered by this code.
    """

    buffer_id: int
    evt_code: int | None
    evt_name: str
    evh_class: str
    mean_height_m: float | None
    dominant_lifeform: str
    pixel_count: int
    area_pct: float


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class LandfireWriter(Protocol):
    """Persists LANDFIRE vegetation structure results to storage."""

    def write_vegetation_structure(
        self,
        results: list[BufferVegetation],
    ) -> int:
        """Write vegetation structure results and return count written."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class PostGISLandfireWriter:
    """Writes LANDFIRE results to silver.buffer_vegetation_structure."""

    _INSERT_SQL = text("""
        INSERT INTO silver.buffer_vegetation_structure
            (buffer_id, evt_code, evt_name, evh_class,
             mean_height_m, dominant_lifeform, pixel_count, area_pct)
        VALUES
            (:buffer_id, :evt_code, :evt_name, :evh_class,
             :mean_height_m, :dominant_lifeform, :pixel_count, :area_pct)
    """)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_vegetation_structure(
        self,
        results: list[BufferVegetation],
    ) -> int:
        """Batch-insert LANDFIRE vegetation structure entries."""
        if not results:
            return 0
        params = [
            {
                "buffer_id": r.buffer_id,
                "evt_code": r.evt_code,
                "evt_name": r.evt_name,
                "evh_class": r.evh_class,
                "mean_height_m": round(r.mean_height_m, 2)
                if r.mean_height_m is not None else None,
                "dominant_lifeform": r.dominant_lifeform,
                "pixel_count": r.pixel_count,
                "area_pct": round(r.area_pct, 2),
            }
            for r in results
        ]
        with self._engine.connect() as conn:
            conn.execute(self._INSERT_SQL, params)
            conn.commit()
        return len(results)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def classify_evt_lifeform(evt_code: int) -> str:
    """Classify an EVT code into a lifeform category.

    Args:
        evt_code: LANDFIRE EVT integer code.

    Returns:
        Lifeform category string (e.g., ``'Tree'``, ``'Shrub'``).
    """
    for code_range, lifeform, _ in EVT_LIFEFORM_RANGES:
        if evt_code in code_range:
            return lifeform
    return "Unknown"


def get_evt_name(evt_code: int) -> str:
    """Look up a human-readable name for an EVT code.

    Falls back to lifeform-based generic names for codes not in the
    notable codes dictionary.

    Args:
        evt_code: LANDFIRE EVT integer code.

    Returns:
        Human-readable EVT name.
    """
    if evt_code in EVT_NOTABLE_CODES:
        return EVT_NOTABLE_CODES[evt_code]
    for code_range, _, desc_prefix in EVT_LIFEFORM_RANGES:
        if evt_code in code_range:
            return f"{desc_prefix} (EVT {evt_code})"
    return f"EVT {evt_code}"


def evh_to_height_m(evh_value: float) -> float:
    """Convert LANDFIRE EVH pixel value to height in meters.

    LF250 EVH encodes height in decimeters (pixel value 10 = 1.0m).

    Args:
        evh_value: Raw EVH pixel value.

    Returns:
        Height in meters.
    """
    return evh_value / 10.0


def classify_evh(mean_height_m: float | None) -> str:
    """Classify mean vegetation height into a descriptive class.

    Args:
        mean_height_m: Mean vegetation height in meters, or None.

    Returns:
        Height class description.
    """
    if mean_height_m is None or mean_height_m <= 0:
        return "No data"
    if mean_height_m < 0.5:
        return "Ground cover (<0.5m)"
    if mean_height_m < 2.0:
        return "Low shrub (0.5–2m)"
    if mean_height_m < 5.0:
        return "Tall shrub (2–5m)"
    if mean_height_m < 15.0:
        return "Sub-canopy (5–15m)"
    if mean_height_m < 25.0:
        return "Canopy (15–25m)"
    return "Tall canopy (>25m)"


def combine_evt_evh(
    evt_stats: list[CategoricalStats],
    evh_stats: list[ContinuousStats],
) -> list[BufferVegetation]:
    """Combine EVT and EVH zonal statistics into vegetation structure entries.

    For each buffer, identifies the dominant EVT code and computes the
    mean vegetation height from EVH data. Produces one summary entry
    per buffer.

    Args:
        evt_stats: Per-buffer EVT class distributions.
        evh_stats: Per-buffer EVH height statistics.

    Returns:
        List of BufferVegetation entries, one per buffer.
    """
    # Build EVH lookup by buffer_id
    evh_lookup: dict[int, ContinuousStats] = {
        s.buffer_id: s for s in evh_stats
    }

    results: list[BufferVegetation] = []
    for evt in evt_stats:
        # Find dominant EVT code (highest pixel count)
        dominant_code = max(evt.class_counts, key=evt.class_counts.get)  # type: ignore[arg-type]
        dominant_count = evt.class_counts[dominant_code]
        dominant_pct = (
            dominant_count / evt.total_pixels * 100
        ) if evt.total_pixels > 0 else 0.0

        # Get EVH stats if available
        evh = evh_lookup.get(evt.buffer_id)
        mean_height_raw = evh.mean if evh else None
        mean_height_m = evh_to_height_m(mean_height_raw) if mean_height_raw else None

        results.append(BufferVegetation(
            buffer_id=evt.buffer_id,
            evt_code=dominant_code,
            evt_name=get_evt_name(dominant_code),
            evh_class=classify_evh(mean_height_m),
            mean_height_m=mean_height_m,
            dominant_lifeform=classify_evt_lifeform(dominant_code),
            pixel_count=dominant_count,
            area_pct=dominant_pct,
        ))

    return results


# ---------------------------------------------------------------------------
# Processor (orchestrator)
# ---------------------------------------------------------------------------


class LandfireProcessor:
    """Orchestrates LANDFIRE vegetation structure extraction for buffers.

    Fetches EVT (type) and EVH (height) rasters for the watershed,
    computes per-buffer statistics, and writes combined results.

    Args:
        evt_source: Raster data source for EVT (categorical).
        evh_source: Raster data source for EVH (continuous).
        writer: Vegetation structure writer.
        engine: SQLAlchemy engine for reading buffer geometries.
    """

    def __init__(
        self,
        evt_source: RasterSource,
        evh_source: RasterSource,
        writer: LandfireWriter,
        engine: Engine,
    ) -> None:
        self._evt_source = evt_source
        self._evh_source = evh_source
        self._writer = writer
        self._engine = engine

    def _load_buffers(self) -> gpd.GeoDataFrame:
        """Load riparian buffer geometries from the silver schema."""
        gdf = gpd.read_postgis(
            "SELECT id, geom FROM silver.riparian_buffers",
            self._engine, geom_col="geom",
        )
        return gdf.rename_geometry("geometry")

    def _load_watershed_bbox(self) -> tuple[float, float, float, float]:
        """Load the watershed bounding box from bronze.watersheds."""
        sql = text(
            "SELECT ST_XMin(geom), ST_YMin(geom), "
            "ST_XMax(geom), ST_YMax(geom) "
            "FROM bronze.watersheds LIMIT 1"
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql).fetchone()
        if row is None:
            raise RuntimeError("No watershed found in bronze.watersheds")
        return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))

    def _truncate_results(self) -> None:
        """Clear existing vegetation structure results."""
        with self._engine.connect() as conn:
            conn.execute(text(  # noqa: S608
                "TRUNCATE silver.buffer_vegetation_structure"
            ))
            conn.commit()

    def process_buffers(self) -> int:
        """Process all riparian buffers for LANDFIRE vegetation structure.

        Steps:
            1. Load buffer geometries and watershed bbox
            2. Fetch EVT and EVH rasters clipped to watershed
            3. Compute per-buffer zonal statistics for each raster
            4. Combine EVT + EVH into vegetation structure entries
            5. Persist to silver.buffer_vegetation_structure

        Returns:
            Number of vegetation structure entries written.
        """
        buffers = self._load_buffers()
        bbox = self._load_watershed_bbox()
        logger.info(
            "Processing LANDFIRE for %d buffers, bbox %s",
            len(buffers), bbox,
        )

        # Fetch both rasters
        logger.info("Fetching LANDFIRE EVT (vegetation type)")
        evt_raster = self._evt_source.fetch(bbox)
        logger.info(
            "EVT raster: shape %s, CRS %s",
            evt_raster.data.shape, evt_raster.crs,
        )

        logger.info("Fetching LANDFIRE EVH (vegetation height)")
        evh_raster = self._evh_source.fetch(bbox)
        logger.info(
            "EVH raster: shape %s, CRS %s",
            evh_raster.data.shape, evh_raster.crs,
        )

        # Compute zonal stats
        evt_stats = compute_categorical_zonal_stats(evt_raster, buffers)
        evh_stats = compute_continuous_zonal_stats(evh_raster, buffers)
        logger.info(
            "EVT stats: %d buffers; EVH stats: %d buffers",
            len(evt_stats), len(evh_stats),
        )

        # Combine and write
        veg_structure = combine_evt_evh(evt_stats, evh_stats)
        logger.info(
            "Generated %d vegetation structure entries",
            len(veg_structure),
        )

        self._truncate_results()
        count = self._writer.write_vegetation_structure(veg_structure)
        logger.info("Wrote %d LANDFIRE vegetation structure entries", count)
        return count
