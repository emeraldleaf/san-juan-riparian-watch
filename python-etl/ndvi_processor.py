"""NDVI vegetation health processor for riparian buffers.

Uses Microsoft Planetary Computer to fetch Sentinel-2 imagery,
clips to buffer geometries with rasterio, computes NDVI statistics,
classifies health with season awareness, and writes results to
silver.vegetation_health.

Study area: San Juan Basin, HUC8 14080101.
Peak growing season: June–August.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

import geopandas as gpd
import numpy as np
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL_2_COLLECTION = "sentinel-2-l2a"
PEAK_GROWING_MONTHS = frozenset({6, 7, 8})  # June–August for San Juan Basin
MAX_CLOUD_COVER = 20  # percent
STORAGE_CRS = "EPSG:4269"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NdviReading:
    """Immutable NDVI reading for a single buffer and acquisition date."""

    buffer_id: int
    acquisition_date: date
    mean_ndvi: float
    min_ndvi: float
    max_ndvi: float
    health_category: str
    season_context: str
    satellite: str = "Sentinel-2"


# ---------------------------------------------------------------------------
# Protocols (interfaces for dependency injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class ImagerySearcher(Protocol):
    """Searches satellite imagery catalogs for items covering a bounding box."""

    def search_items(
        self,
        bbox: tuple[float, float, float, float],
        date_range: str,
        max_cloud_cover: int,
    ) -> list[Any]:
        """Return STAC items matching the spatial and temporal criteria."""
        ...


@runtime_checkable
class NdviWriter(Protocol):
    """Persists NDVI readings to storage."""

    def write_readings(self, readings: list[NdviReading]) -> int:
        """Write readings and return the count written."""
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class PlanetaryComputerSearcher:
    """Searches Planetary Computer STAC for Sentinel-2 L2A imagery.

    Uses ``planetary_computer.sign_inplace`` to authenticate asset
    URLs for direct access via rasterio.
    """

    def __init__(self, stac_url: str = STAC_API_URL) -> None:
        self._catalog = pystac_client.Client.open(stac_url)

    def search_items(
        self,
        bbox: tuple[float, float, float, float],
        date_range: str,
        max_cloud_cover: int,
    ) -> list[Any]:
        """Search for Sentinel-2 items and sign asset URLs in-place."""
        search = self._catalog.search(
            collections=[SENTINEL_2_COLLECTION],
            bbox=bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
        )
        items = list(search.items())
        for item in items:
            planetary_computer.sign_inplace(item)
        logger.debug("Found %d Sentinel-2 items for bbox %s", len(items), bbox)
        return items


class PostGISNdviWriter:
    """Writes NDVI readings to silver.vegetation_health in PostGIS."""

    _INSERT_SQL = text("""
        INSERT INTO silver.vegetation_health
            (buffer_id, acquisition_date, mean_ndvi, min_ndvi, max_ndvi,
             health_category, season_context, satellite)
        VALUES
            (:buffer_id, :acquisition_date, :mean_ndvi, :min_ndvi, :max_ndvi,
             :health_category, :season_context, :satellite)
        ON CONFLICT (buffer_id, acquisition_date, satellite) DO NOTHING
    """)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_readings(self, readings: list[NdviReading]) -> int:
        """Batch-insert readings into vegetation_health table."""
        if not readings:
            return 0
        params = [
            {
                "buffer_id": r.buffer_id,
                "acquisition_date": r.acquisition_date,
                "mean_ndvi": r.mean_ndvi,
                "min_ndvi": r.min_ndvi,
                "max_ndvi": r.max_ndvi,
                "health_category": r.health_category,
                "season_context": r.season_context,
                "satellite": r.satellite,
            }
            for r in readings
        ]
        with self._engine.connect() as conn:
            conn.execute(self._INSERT_SQL, params)
            conn.commit()
        return len(readings)


# ---------------------------------------------------------------------------
# Pure functions (no I/O, always testable)
# ---------------------------------------------------------------------------


def determine_season(acquisition_date: date) -> str:
    """Determine season context for a given date.

    Peak growing season for the San Juan Basin is June–August.

    Args:
        acquisition_date: The imagery acquisition date.

    Returns:
        ``'peak_growing'`` or ``'dormant'``.
    """
    if acquisition_date.month in PEAK_GROWING_MONTHS:
        return "peak_growing"
    return "dormant"


def classify_health(mean_ndvi: float, season: str) -> str:
    """Classify vegetation health from NDVI and season context.

    Thresholds: healthy (>0.6), degraded (0.3–0.6), bare (<0.3).
    Dormant-season readings are always classified as ``'dormant'``,
    never ``'bare'``.

    Args:
        mean_ndvi: Mean NDVI value for the buffer.
        season: Season context (``'peak_growing'`` or ``'dormant'``).

    Returns:
        Health category: ``'healthy'``, ``'degraded'``, ``'bare'``,
        or ``'dormant'``.
    """
    if season == "dormant":
        return "dormant"
    if mean_ndvi > 0.6:
        return "healthy"
    if mean_ndvi >= 0.3:
        return "degraded"
    return "bare"


def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Calculate NDVI from NIR and Red band arrays.

    NDVI = (NIR - Red) / (NIR + Red), range [-1, +1].

    Args:
        nir: Near-infrared band values (Sentinel-2 B08).
        red: Red band values (Sentinel-2 B04).

    Returns:
        NDVI array with invalid pixels set to 0.0.
    """
    nir_f = nir.astype(np.float64)
    red_f = red.astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir_f - red_f) / (nir_f + red_f)
    return np.where(np.isfinite(ndvi), ndvi, 0.0)


def compute_ndvi_stats(ndvi: np.ndarray) -> tuple[float, float, float]:
    """Compute mean, min, max from an NDVI array.

    Filters to valid values in [-1, 1].

    Args:
        ndvi: NDVI array.

    Returns:
        Tuple of (mean, min, max). Returns ``(0, 0, 0)`` if no valid pixels.
    """
    valid = ndvi[(ndvi >= -1) & (ndvi <= 1) & np.isfinite(ndvi)]
    if valid.size == 0:
        return (0.0, 0.0, 0.0)
    return (float(np.mean(valid)), float(np.min(valid)), float(np.max(valid)))


def reproject_geometry(
    geom: BaseGeometry, src_crs: str, dst_crs: str,
) -> BaseGeometry:
    """Reproject a Shapely geometry between coordinate reference systems.

    Args:
        geom: Input geometry.
        src_crs: Source CRS (e.g., ``'EPSG:4269'``).
        dst_crs: Destination CRS.

    Returns:
        Reprojected geometry.
    """
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def clip_band_to_geometry(href: str, geom: BaseGeometry) -> np.ndarray:
    """Clip a raster band to a geometry using rasterio.

    Reprojects the geometry from EPSG:4269 to the raster's CRS before
    clipping with ``rasterio.mask.mask()``.

    Args:
        href: URL or file path to the raster band (COG).
        geom: Shapely geometry in EPSG:4269.

    Returns:
        Clipped raster values as a 2D numpy array.
    """
    with rasterio.open(href) as src:
        raster_crs = str(src.crs)
        if raster_crs.upper() != STORAGE_CRS:
            geom = reproject_geometry(geom, STORAGE_CRS, raster_crs)
        clipped, _ = rasterio_mask(src, [mapping(geom)], crop=True, nodata=0)
    return clipped[0]


# ---------------------------------------------------------------------------
# STAC item parsing
# ---------------------------------------------------------------------------


def _parse_stac_item(item: Any) -> tuple[str, str, date] | None:
    """Extract NIR href, Red href, and acquisition date from a STAC item.

    Args:
        item: A signed pystac Item with Sentinel-2 L2A assets.

    Returns:
        Tuple of ``(nir_href, red_href, acquisition_date)``, or ``None``
        if the item is missing required bands or datetime.
    """
    try:
        nir_href = item.assets["B08"].href
        red_href = item.assets["B04"].href
    except KeyError:
        logger.warning("Skipping item %s: missing B04/B08 bands", item.id)
        return None
    if item.datetime is None:
        logger.warning("Skipping item %s: no acquisition datetime", item.id)
        return None
    return (nir_href, red_href, item.datetime.date())


# ---------------------------------------------------------------------------
# Processor (orchestrator)
# ---------------------------------------------------------------------------


class NdviProcessor:
    """Orchestrates NDVI computation for all riparian buffers.

    Fetches Sentinel-2 imagery from Planetary Computer, clips to buffer
    geometries, computes NDVI statistics, classifies health with season
    awareness (peak growing June–Aug, dormant otherwise), and writes
    results to ``silver.vegetation_health``.

    Uses constructor injection for all I/O dependencies so each step
    can be tested with fake searchers and writers.

    Args:
        searcher: Imagery catalog searcher.
        writer: NDVI reading writer.
        engine: SQLAlchemy engine for reading buffer geometries.
    """

    def __init__(
        self,
        searcher: ImagerySearcher,
        writer: NdviWriter,
        engine: Engine,
    ) -> None:
        self._searcher = searcher
        self._writer = writer
        self._engine = engine

    def process_buffers(
        self,
        date_range: str,
        max_cloud_cover: int = MAX_CLOUD_COVER,
    ) -> int:
        """Process all riparian buffers for NDVI vegetation health.

        Args:
            date_range: STAC datetime range (e.g., ``'2024-06-01/2024-08-31'``).
            max_cloud_cover: Maximum cloud cover percentage.

        Returns:
            Number of NDVI readings written.
        """
        buffers = self._load_buffers()
        logger.info("Processing NDVI for %d buffers", len(buffers))

        all_readings: list[NdviReading] = []
        for _, row in buffers.iterrows():
            readings = self._process_single_buffer(
                row, date_range, max_cloud_cover,
            )
            all_readings.extend(readings)

        count = self._writer.write_readings(all_readings)
        logger.info("Wrote %d NDVI readings to vegetation_health", count)
        return count

    def _load_buffers(self) -> gpd.GeoDataFrame:
        """Load riparian buffer geometries from the silver schema."""
        return gpd.read_postgis(
            "SELECT id, geom FROM silver.riparian_buffers",
            self._engine, geom_col="geom",
        )

    def _process_single_buffer(
        self,
        buffer_row: Any,
        date_range: str,
        max_cloud_cover: int,
    ) -> list[NdviReading]:
        """Process NDVI for one buffer across all available imagery."""
        buffer_id = int(buffer_row["id"])
        geom: BaseGeometry = buffer_row.geometry
        bbox = geom.bounds

        items = self._searcher.search_items(bbox, date_range, max_cloud_cover)
        if not items:
            logger.debug("No imagery found for buffer %d", buffer_id)
            return []

        readings: list[NdviReading] = []
        for item in items:
            reading = self._compute_reading(buffer_id, geom, item)
            if reading is not None:
                readings.append(reading)
        return readings

    def _compute_reading(
        self, buffer_id: int, geom: BaseGeometry, item: Any,
    ) -> NdviReading | None:
        """Compute a single NDVI reading from a STAC item clipped to a buffer."""
        parsed = _parse_stac_item(item)
        if parsed is None:
            return None
        nir_href, red_href, acq_date = parsed

        try:
            nir = clip_band_to_geometry(nir_href, geom)
            red = clip_band_to_geometry(red_href, geom)
        except (rasterio.RasterioIOError, ValueError):
            logger.warning(
                "Failed to clip imagery for buffer %d from %s",
                buffer_id, item.id,
            )
            return None

        ndvi = calculate_ndvi(nir, red)
        mean_val, min_val, max_val = compute_ndvi_stats(ndvi)
        season = determine_season(acq_date)

        return NdviReading(
            buffer_id=buffer_id,
            acquisition_date=acq_date,
            mean_ndvi=round(mean_val, 4),
            min_ndvi=round(min_val, 4),
            max_ndvi=round(max_val, 4),
            health_category=classify_health(mean_val, season),
            season_context=season,
        )

    # -- Incremental processing ---------------------------------------------

    def get_last_ndvi_date(self) -> date | None:
        """Get the most recent acquisition_date from vegetation_health.

        Returns:
            Most recent date, or None if no readings exist.
        """
        sql = text(
            "SELECT MAX(acquisition_date) FROM silver.vegetation_health"
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] else None

    def get_processed_keys(self) -> set[tuple[int, str, str]]:
        """Get already-processed (buffer_id, date, satellite) combinations.

        Returns:
            Set of (buffer_id, date_string, satellite) tuples.
        """
        sql = text("""
            SELECT buffer_id, acquisition_date::TEXT, satellite
            FROM silver.vegetation_health
        """)
        with self._engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return {(r[0], r[1], r[2]) for r in rows}

    def process_buffers_incremental(
        self,
        max_cloud_cover: int = MAX_CLOUD_COVER,
    ) -> int:
        """Process NDVI incrementally, skipping already-processed dates.

        Auto-detects the date range: from the day after the last
        processed acquisition date through today. Falls back to the
        current year's growing season if no prior data exists.

        Args:
            max_cloud_cover: Maximum cloud cover percentage.

        Returns:
            Number of new NDVI readings written.
        """
        from datetime import datetime, timedelta

        last_date = self.get_last_ndvi_date()
        if last_date:
            start = last_date + timedelta(days=1)
        else:
            # Default: start of current year's growing season
            start = date(datetime.now().year, 6, 1)

        end = date.today()
        if start > end:
            logger.info("NDVI is up-to-date through %s — nothing to process", last_date)
            return 0

        date_range = f"{start.isoformat()}/{end.isoformat()}"
        logger.info("Incremental NDVI processing: %s", date_range)

        processed = self.get_processed_keys()
        buffers = self._load_buffers()
        logger.info(
            "Processing NDVI for %d buffers (%d existing readings to skip)",
            len(buffers), len(processed),
        )

        all_readings: list[NdviReading] = []
        for _, row in buffers.iterrows():
            readings = self._process_single_buffer_incremental(
                row, date_range, max_cloud_cover, processed,
            )
            all_readings.extend(readings)

        count = self._writer.write_readings(all_readings)
        logger.info("Wrote %d new NDVI readings", count)
        return count

    def _process_single_buffer_incremental(
        self,
        buffer_row: Any,
        date_range: str,
        max_cloud_cover: int,
        processed: set[tuple[int, str, str]],
    ) -> list[NdviReading]:
        """Process NDVI for one buffer, skipping already-processed items."""
        buffer_id = int(buffer_row["id"])
        geom: BaseGeometry = buffer_row.geometry
        bbox = geom.bounds

        items = self._searcher.search_items(bbox, date_range, max_cloud_cover)
        if not items:
            return []

        readings: list[NdviReading] = []
        for item in items:
            parsed = _parse_stac_item(item)
            if parsed is None:
                continue
            _, _, acq_date = parsed
            key = (buffer_id, str(acq_date), "Sentinel-2")
            if key in processed:
                continue
            reading = self._compute_reading(buffer_id, geom, item)
            if reading is not None:
                readings.append(reading)
        return readings
