"""NDVI vegetation health processor for riparian buffers.

Uses Microsoft Planetary Computer to fetch Sentinel-2 imagery,
clips to buffer geometries with rasterio, computes NDVI statistics,
classifies health with season awareness, and writes results to
silver.vegetation_health.

Scene-first processing: one STAC search for the whole watershed,
then iterate scenes and extract per-buffer stats in memory via
``rasterio.features.geometry_mask()``.

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
import rasterio.windows
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.mask import mask as rasterio_mask
from rasterio.windows import from_bounds as window_from_bounds
from shapely.geometry import box, mapping
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

    Thresholds calibrated for the semi-arid San Juan Basin (HUC8 14080101)
    where peak-growing median NDVI is ~0.17:

    - **healthy** (>0.3): Actual riparian vegetation with measurable canopy.
    - **degraded** (0.15–0.3): Sparse cover, grasses, or stressed vegetation.
    - **bare** (<0.15): Exposed soil, rock, or water with minimal vegetation.

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
    if mean_ndvi > 0.3:
        return "healthy"
    if mean_ndvi >= 0.15:
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

    Note:
        Retained for ad-hoc single-buffer use. The main pipeline uses
        ``read_band_window()`` + ``geometry_mask()`` for scene-first
        batch processing.

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
# Scene-first raster I/O
# ---------------------------------------------------------------------------


def read_band_window(
    href: str,
    watershed_bbox: tuple[float, float, float, float],
    watershed_crs: str = STORAGE_CRS,
    overview_level: int | None = 1,
) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Read a raster band windowed to the watershed bounding box.

    Opens the COG once and reads only the pixels covering the watershed,
    avoiding full-scene downloads. Uses overview levels to reduce data
    transfer (level 1 = 20m for Sentinel-2, level 2 = 40m).

    Args:
        href: URL or file path to the raster band (COG).
        watershed_bbox: ``(minx, miny, maxx, maxy)`` in *watershed_crs*.
        watershed_crs: CRS of the watershed bbox (default EPSG:4269).
        overview_level: COG overview level (0=full, 1=2x, 2=4x). Default
            1 (20m for Sentinel-2 10m bands). None for full resolution.

    Returns:
        Tuple of ``(data_2d, window_transform, cog_crs_string)``.

    Raises:
        rasterio.RasterioIOError: If the COG cannot be opened or read.
    """
    open_kwargs: dict[str, Any] = {}
    if overview_level is not None:
        open_kwargs["overview_level"] = overview_level

    with rasterio.open(href, **open_kwargs) as src:
        cog_crs = str(src.crs)
        if cog_crs.upper() != watershed_crs.upper():
            bbox_geom = box(*watershed_bbox)
            bbox_reprojected = reproject_geometry(
                bbox_geom, watershed_crs, cog_crs,
            )
            bounds = bbox_reprojected.bounds
        else:
            bounds = watershed_bbox

        window = window_from_bounds(*bounds, transform=src.transform)
        # Clamp to raster extent — scene may not cover full watershed
        window = window.intersection(
            rasterio.windows.Window(0, 0, src.width, src.height),
        )
        data = src.read(1, window=window)
        transform = src.window_transform(window)
    return (data, transform, cog_crs)


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
# Processor (orchestrator) — scene-first approach
# ---------------------------------------------------------------------------


class NdviProcessor:
    """Orchestrates NDVI computation for all riparian buffers.

    Uses a **scene-first** approach: one STAC search for the whole
    watershed, then for each scene reads two bands into memory and
    extracts per-buffer stats via ``rasterio.features.geometry_mask()``.
    This reduces HTTP requests from ~256K to ~128 for 2000 buffers.

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

    # -- Data loading -------------------------------------------------------

    def _load_buffers(self) -> gpd.GeoDataFrame:
        """Load riparian buffer geometries from the silver schema."""
        gdf = gpd.read_postgis(
            "SELECT id, geom FROM silver.riparian_buffers",
            self._engine, geom_col="geom",
        )
        gdf = gdf.rename_geometry("geometry")
        return gdf

    def _load_watershed_bbox(self) -> tuple[float, float, float, float]:
        """Load the bounding box of the watershed from bronze.watersheds.

        Returns:
            ``(minx, miny, maxx, maxy)`` in EPSG:4269.

        Raises:
            RuntimeError: If no watershed exists in the database.
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

    # -- Scene-first full processing ----------------------------------------

    def process_buffers(
        self,
        date_range: str,
        max_cloud_cover: int = MAX_CLOUD_COVER,
    ) -> int:
        """Process all riparian buffers for NDVI vegetation health.

        Delegates to scene-first processing for efficiency.

        Args:
            date_range: STAC datetime range (e.g., ``'2024-06-01/2024-08-31'``).
            max_cloud_cover: Maximum cloud cover percentage.

        Returns:
            Number of NDVI readings written.
        """
        return self.process_buffers_by_scene(date_range, max_cloud_cover)

    def process_buffers_by_scene(
        self,
        date_range: str,
        max_cloud_cover: int = MAX_CLOUD_COVER,
    ) -> int:
        """Process all buffers using scene-first NDVI computation.

        One STAC search for the watershed bbox, then iterate scenes and
        extract per-buffer stats in memory.

        Args:
            date_range: STAC datetime range (e.g., ``'2025-06-01/2025-08-31'``).
            max_cloud_cover: Maximum cloud cover percentage.

        Returns:
            Number of NDVI readings written.
        """
        buffers = self._load_buffers()
        watershed_bbox = self._load_watershed_bbox()
        logger.info(
            "Scene-first NDVI: %d buffers, watershed bbox %s",
            len(buffers), watershed_bbox,
        )

        items = self._searcher.search_items(
            watershed_bbox, date_range, max_cloud_cover,
        )
        if not items:
            logger.warning(
                "No Sentinel-2 imagery found for date range %s", date_range,
            )
            return 0
        logger.info("Found %d Sentinel-2 scenes to process", len(items))

        all_readings: list[NdviReading] = []
        for scene_idx, item in enumerate(items, start=1):
            parsed = _parse_stac_item(item)
            if parsed is None:
                continue
            nir_href, red_href, acq_date = parsed

            logger.info(
                "Processing scene %d/%d: %s (acquired %s)",
                scene_idx, len(items), item.id, acq_date,
            )

            try:
                readings = self._process_scene(
                    nir_href, red_href, acq_date, item,
                    buffers, watershed_bbox,
                )
                all_readings.extend(readings)
            except (rasterio.RasterioIOError, ValueError) as exc:
                logger.warning(
                    "Failed to process scene %s: %s", item.id, exc,
                )
                continue

            logger.info(
                "  Scene %s: %d readings", item.id, len(readings),
            )

        count = self._writer.write_readings(all_readings)
        logger.info("Wrote %d NDVI readings to vegetation_health", count)
        return count

    # -- Per-scene processing -----------------------------------------------

    def _process_scene(
        self,
        nir_href: str,
        red_href: str,
        acq_date: date,
        item: Any,
        buffers: gpd.GeoDataFrame,
        watershed_bbox: tuple[float, float, float, float],
    ) -> list[NdviReading]:
        """Process a single Sentinel-2 scene against all buffers.

        Opens B08 and B04 once each (2 HTTP requests), computes
        full-scene NDVI, then extracts per-buffer stats in memory.

        Args:
            nir_href: URL to the NIR (B08) COG.
            red_href: URL to the Red (B04) COG.
            acq_date: Image acquisition date.
            item: STAC item (for bbox filtering).
            buffers: All buffer geometries in STORAGE_CRS.
            watershed_bbox: Watershed bounding box in STORAGE_CRS.

        Returns:
            List of NdviReading for all buffers covered by this scene.
        """
        nir_data, transform, cog_crs = read_band_window(
            nir_href, watershed_bbox,
        )
        red_data, _, _ = read_band_window(red_href, watershed_bbox)

        ndvi_array = calculate_ndvi(nir_data, red_data)
        season = determine_season(acq_date)

        # Pre-filter buffers to those intersecting this scene's footprint
        scene_bbox = tuple(item.bbox) if item.bbox else watershed_bbox
        relevant = self._buffers_intersecting_scene(buffers, scene_bbox)
        logger.debug(
            "Scene covers %d of %d buffers", len(relevant), len(buffers),
        )

        # Create transformer once per scene (not per buffer)
        need_reproject = cog_crs.upper() != STORAGE_CRS.upper()
        transformer: Transformer | None = None
        if need_reproject:
            transformer = Transformer.from_crs(
                STORAGE_CRS, cog_crs, always_xy=True,
            )

        readings: list[NdviReading] = []
        for _, row in relevant.iterrows():
            reading = self._extract_buffer_reading(
                int(row["id"]), row.geometry, ndvi_array, transform,
                acq_date, season, transformer,
            )
            if reading is not None:
                readings.append(reading)

        return readings

    def _process_scene_incremental(
        self,
        nir_href: str,
        red_href: str,
        acq_date: date,
        item: Any,
        buffers: gpd.GeoDataFrame,
        watershed_bbox: tuple[float, float, float, float],
        processed: set[tuple[int, str, str]],
    ) -> list[NdviReading]:
        """Process a scene incrementally, skipping already-processed buffers.

        Same as ``_process_scene`` but checks the *processed* set before
        computing stats for each buffer. If all buffers are already
        processed for this acquisition date, skips the expensive band
        reads entirely.

        Args:
            nir_href: URL to the NIR (B08) COG.
            red_href: URL to the Red (B04) COG.
            acq_date: Image acquisition date.
            item: STAC item.
            buffers: All buffer geometries in STORAGE_CRS.
            watershed_bbox: Watershed bounding box in STORAGE_CRS.
            processed: Set of ``(buffer_id, date_str, satellite)`` already in DB.

        Returns:
            List of new NdviReading objects (skips already-processed).
        """
        acq_date_str = str(acq_date)

        # Quick check: skip the scene entirely if all buffers are done
        buffer_ids = set(buffers["id"].astype(int))
        unprocessed = {
            bid for bid in buffer_ids
            if (bid, acq_date_str, "Sentinel-2") not in processed
        }
        if not unprocessed:
            logger.debug(
                "All buffers already processed for %s — skipping scene",
                acq_date,
            )
            return []

        nir_data, transform, cog_crs = read_band_window(
            nir_href, watershed_bbox,
        )
        red_data, _, _ = read_band_window(red_href, watershed_bbox)

        ndvi_array = calculate_ndvi(nir_data, red_data)
        season = determine_season(acq_date)

        scene_bbox = tuple(item.bbox) if item.bbox else watershed_bbox
        relevant = self._buffers_intersecting_scene(buffers, scene_bbox)

        need_reproject = cog_crs.upper() != STORAGE_CRS.upper()
        transformer: Transformer | None = None
        if need_reproject:
            transformer = Transformer.from_crs(
                STORAGE_CRS, cog_crs, always_xy=True,
            )

        readings: list[NdviReading] = []
        skipped = 0
        for _, row in relevant.iterrows():
            buffer_id = int(row["id"])
            key = (buffer_id, acq_date_str, "Sentinel-2")
            if key in processed:
                skipped += 1
                continue

            reading = self._extract_buffer_reading(
                buffer_id, row.geometry, ndvi_array, transform,
                acq_date, season, transformer,
            )
            if reading is not None:
                readings.append(reading)

        if skipped > 0:
            logger.debug(
                "Skipped %d already-processed buffers for %s", skipped, acq_date,
            )
        return readings

    # -- Per-buffer extraction (in-memory, no I/O) --------------------------

    @staticmethod
    def _extract_buffer_reading(
        buffer_id: int,
        geom: BaseGeometry,
        ndvi_array: np.ndarray,
        transform: rasterio.Affine,
        acq_date: date,
        season: str,
        transformer: Transformer | None,
    ) -> NdviReading | None:
        """Extract NDVI stats for one buffer from a full-scene NDVI array.

        Uses ``rasterio.features.geometry_mask()`` for in-memory masking
        — no HTTP I/O.

        Args:
            buffer_id: Buffer primary key.
            geom: Buffer geometry in STORAGE_CRS.
            ndvi_array: Full-scene NDVI array.
            transform: Affine transform of the NDVI array.
            acq_date: Image acquisition date.
            season: Season context string.
            transformer: Optional CRS transformer (STORAGE_CRS → COG CRS).

        Returns:
            NdviReading or None if no valid pixels in the buffer.
        """
        if transformer is not None:
            geom = shapely_transform(transformer.transform, geom)

        try:
            mask = geometry_mask(
                [mapping(geom)],
                out_shape=ndvi_array.shape,
                transform=transform,
                invert=True,
            )
        except (ValueError, IndexError):
            return None

        buffer_pixels = ndvi_array[mask]
        if buffer_pixels.size == 0:
            return None

        mean_val, min_val, max_val = compute_ndvi_stats(buffer_pixels)
        return NdviReading(
            buffer_id=buffer_id,
            acquisition_date=acq_date,
            mean_ndvi=round(mean_val, 4),
            min_ndvi=round(min_val, 4),
            max_ndvi=round(max_val, 4),
            health_category=classify_health(mean_val, season),
            season_context=season,
        )

    @staticmethod
    def _buffers_intersecting_scene(
        buffers: gpd.GeoDataFrame,
        scene_bbox: tuple[float, ...],
    ) -> gpd.GeoDataFrame:
        """Filter buffers to those whose geometry intersects the scene bbox.

        Uses GeoPandas spatial predicates for fast filtering.

        Args:
            buffers: GeoDataFrame with geometry column in STORAGE_CRS.
            scene_bbox: ``(minx, miny, maxx, maxy)`` of the scene footprint.

        Returns:
            Filtered GeoDataFrame (subset of rows).
        """
        scene_box = box(*scene_bbox[:4])
        intersects_mask = buffers.geometry.intersects(scene_box)
        return buffers[intersects_mask]

    # -- Incremental processing (scene-first) --------------------------------

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
        """Process NDVI incrementally using scene-first approach.

        Auto-detects the date range from the last processed acquisition
        date. Skips already-processed (buffer_id, date, satellite)
        combinations.

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
            start = date(datetime.now().year, 6, 1)

        end = date.today()
        if start > end:
            logger.info(
                "NDVI is up-to-date through %s — nothing to process",
                last_date,
            )
            return 0

        date_range = f"{start.isoformat()}/{end.isoformat()}"
        logger.info("Incremental NDVI processing (scene-first): %s", date_range)

        processed = self.get_processed_keys()
        buffers = self._load_buffers()
        watershed_bbox = self._load_watershed_bbox()

        logger.info(
            "Processing NDVI for %d buffers (%d existing readings to skip)",
            len(buffers), len(processed),
        )

        items = self._searcher.search_items(
            watershed_bbox, date_range, max_cloud_cover,
        )
        if not items:
            logger.info("No new Sentinel-2 imagery found")
            return 0
        logger.info("Found %d scenes for incremental processing", len(items))

        all_readings: list[NdviReading] = []
        for scene_idx, item in enumerate(items, start=1):
            parsed = _parse_stac_item(item)
            if parsed is None:
                continue
            nir_href, red_href, acq_date = parsed

            logger.info(
                "Processing scene %d/%d: %s (acquired %s)",
                scene_idx, len(items), item.id, acq_date,
            )

            try:
                readings = self._process_scene_incremental(
                    nir_href, red_href, acq_date, item,
                    buffers, watershed_bbox, processed,
                )
                all_readings.extend(readings)
            except (rasterio.RasterioIOError, ValueError) as exc:
                logger.warning(
                    "Failed to process scene %s: %s", item.id, exc,
                )
                continue

            logger.info(
                "  Scene %s: %d new readings", item.id, len(readings),
            )

        count = self._writer.write_readings(all_readings)
        logger.info("Wrote %d new NDVI readings", count)
        return count
