"""NLCD land cover processor for riparian buffers.

Downloads NLCD (National Land Cover Database) data from the MRLC
ArcGIS ImageServer, clips to the watershed bounding box, and computes
per-buffer land cover class distributions using zonal statistics.

Uses the raster_processor framework for data fetching and masking.

Study area: San Juan Basin, HUC8 14080101.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from raster_processor import (
    CategoricalStats,
    ImageServerSource,
    RasterResult,
    RasterSource,
    compute_categorical_zonal_stats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# MRLC ArcGIS ImageServer for Annual NLCD Land Cover (CONUS)
# This endpoint supports exportImage with GeoTIFF output.
NLCD_IMAGE_SERVER_URL = (
    "https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/ows"
)

# Fallback: Use the USGS EROS ArcGIS ImageServer for NLCD
# The MRLC geoserver sometimes has issues; this is a more reliable alternative
NLCD_EROS_URL = (
    "https://eros.usgs.gov/lcms/rest/services/NLCD/NLCD_Land_Cover/ImageServer"
)

# Current NLCD vintage
NLCD_YEAR = 2021

# NLCD class definitions: code → (description, is_natural)
# Based on Anderson Level II classification
NLCD_CLASSES: dict[int, tuple[str, bool]] = {
    11: ("Open Water", False),
    12: ("Perennial Ice/Snow", False),
    21: ("Developed, Open Space", False),
    22: ("Developed, Low Intensity", False),
    23: ("Developed, Medium Intensity", False),
    24: ("Developed, High Intensity", False),
    31: ("Barren Land", False),
    41: ("Deciduous Forest", True),
    42: ("Evergreen Forest", True),
    43: ("Mixed Forest", True),
    51: ("Dwarf Scrub", True),
    52: ("Shrub/Scrub", True),
    71: ("Grassland/Herbaceous", True),
    72: ("Sedge/Herbaceous", True),
    73: ("Lichens", True),
    74: ("Moss", True),
    81: ("Pasture/Hay", False),
    82: ("Cultivated Crops", False),
    90: ("Woody Wetlands", True),
    95: ("Emergent Herbaceous Wetlands", True),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BufferLandCover:
    """A single NLCD class entry for a buffer.

    Attributes:
        buffer_id: Buffer primary key.
        nlcd_class: NLCD class code.
        nlcd_description: Human-readable class name.
        pixel_count: Number of pixels of this class.
        area_pct: Percentage of buffer area covered by this class.
        is_natural: Whether this class represents natural land cover.
    """

    buffer_id: int
    nlcd_class: int
    nlcd_description: str
    pixel_count: int
    area_pct: float
    is_natural: bool


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class NlcdWriter(Protocol):
    """Persists NLCD land cover results to storage."""

    def write_land_cover(
        self,
        results: list[BufferLandCover],
    ) -> int:
        """Write land cover results and return count written."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class PostGISNlcdWriter:
    """Writes NLCD results to silver.buffer_land_cover in PostGIS."""

    _INSERT_SQL = text("""
        INSERT INTO silver.buffer_land_cover
            (buffer_id, nlcd_class, nlcd_description, pixel_count,
             area_pct, is_natural, acquisition_year)
        VALUES
            (:buffer_id, :nlcd_class, :nlcd_description, :pixel_count,
             :area_pct, :is_natural, :acquisition_year)
    """)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_land_cover(
        self,
        results: list[BufferLandCover],
    ) -> int:
        """Batch-insert NLCD land cover entries."""
        if not results:
            return 0
        params = [
            {
                "buffer_id": r.buffer_id,
                "nlcd_class": r.nlcd_class,
                "nlcd_description": r.nlcd_description,
                "pixel_count": r.pixel_count,
                "area_pct": round(r.area_pct, 2),
                "is_natural": r.is_natural,
                "acquisition_year": NLCD_YEAR,
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


def stats_to_land_cover(
    stats_list: list[CategoricalStats],
) -> list[BufferLandCover]:
    """Convert categorical zonal statistics to BufferLandCover entries.

    For each buffer, creates one entry per NLCD class found, with
    area percentage computed relative to total valid pixels.

    Args:
        stats_list: Output from ``compute_categorical_zonal_stats()``.

    Returns:
        Flat list of BufferLandCover entries across all buffers.
    """
    results: list[BufferLandCover] = []
    for stats in stats_list:
        for class_code, count in sorted(stats.class_counts.items()):
            desc, is_natural = NLCD_CLASSES.get(
                class_code, (f"Unknown ({class_code})", False),
            )
            area_pct = (count / stats.total_pixels * 100) if stats.total_pixels > 0 else 0.0
            results.append(BufferLandCover(
                buffer_id=stats.buffer_id,
                nlcd_class=class_code,
                nlcd_description=desc,
                pixel_count=count,
                area_pct=area_pct,
                is_natural=is_natural,
            ))
    return results


# ---------------------------------------------------------------------------
# Processor (orchestrator)
# ---------------------------------------------------------------------------


class NlcdProcessor:
    """Orchestrates NLCD land cover extraction for riparian buffers.

    Fetches the NLCD raster for the watershed extent, then computes
    per-buffer land cover class distributions using categorical zonal
    statistics.

    Args:
        source: Raster data source for NLCD.
        writer: NLCD land cover writer.
        engine: SQLAlchemy engine for reading buffer geometries.
    """

    def __init__(
        self,
        source: RasterSource,
        writer: NlcdWriter,
        engine: Engine,
    ) -> None:
        self._source = source
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
        """Load the watershed bounding box from bronze.watersheds.

        Returns:
            ``(minx, miny, maxx, maxy)`` in EPSG:4269.
        """
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
        """Clear existing NLCD results before reprocessing."""
        with self._engine.connect() as conn:
            conn.execute(text(  # noqa: S608
                "TRUNCATE silver.buffer_land_cover"
            ))
            conn.commit()

    def process_buffers(self) -> int:
        """Process all riparian buffers for NLCD land cover.

        Steps:
            1. Load buffer geometries and watershed bbox
            2. Fetch NLCD raster clipped to watershed
            3. Compute per-buffer categorical zonal stats
            4. Convert to land cover entries and persist

        Returns:
            Number of land cover entries written.
        """
        buffers = self._load_buffers()
        bbox = self._load_watershed_bbox()
        logger.info(
            "Processing NLCD for %d buffers, bbox %s",
            len(buffers), bbox,
        )

        # Fetch raster
        raster = self._source.fetch(bbox)
        logger.info(
            "NLCD raster: %s, shape %s",
            raster.crs, raster.data.shape,
        )

        # Compute categorical stats
        cat_stats = compute_categorical_zonal_stats(raster, buffers)

        # Convert to land cover entries
        land_cover = stats_to_land_cover(cat_stats)
        logger.info(
            "Generated %d land cover entries for %d buffers",
            len(land_cover), len(cat_stats),
        )

        # Persist
        self._truncate_results()
        count = self._writer.write_land_cover(land_cover)
        logger.info("Wrote %d NLCD land cover entries", count)
        return count
