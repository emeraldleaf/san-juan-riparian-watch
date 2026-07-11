"""USGS 3DEP LiDAR canopy height processor.

Queries Planetary Computer STAC for 3DEP LiDAR-derived DSM (Digital Surface
Model) and DTM (Digital Terrain Model) tiles, computes a Canopy Height Model
(CHM = DSM - DTM) clipped to each riparian buffer, and writes per-buffer
canopy height statistics to ``silver.buffer_canopy``.

Statistical outputs per buffer:
  - mean_height_m   – average canopy height across the buffer
  - max_height_m    – maximum canopy height
  - p95_height_m    – 95th percentile canopy height (robust max)
  - canopy_cover_pct – percentage of buffer area with height > 2 m
  - height_std_dev  – standard deviation of canopy heights

Uses scene-first access: reads raster windows covering the full watershed
bounding box once, then clips per-buffer via geometry masks.
"""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd
import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds as window_from_bounds
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform as shapely_transform
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
STORAGE_CRS = "EPSG:4269"

# 3DEP collections on Planetary Computer
DSM_COLLECTION = "3dep-lidar-dsm"
DTM_COLLECTION = "3dep-lidar-dtm-native"

# Minimum canopy height threshold (meters) for cover percentage
CANOPY_HEIGHT_THRESHOLD = 2.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _reproject_geometry(
    geom: Any,
    from_crs: str,
    to_crs: str,
) -> Any:
    """Reproject a shapely geometry between CRS using pyproj."""
    transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def _read_raster_window(
    href: str,
    bbox: tuple[float, float, float, float],
    bbox_crs: str = STORAGE_CRS,
) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Read a raster band windowed to a bounding box.

    Opens the COG once and reads only the pixels within the bbox.

    Returns:
        Tuple of (data_2d, window_transform, raster_crs_string).
    """
    with rasterio.open(href) as src:
        raster_crs = str(src.crs)
        if raster_crs.upper() != bbox_crs.upper():
            bbox_geom = box(*bbox)
            bbox_reprojected = _reproject_geometry(bbox_geom, bbox_crs, raster_crs)
            bounds = bbox_reprojected.bounds
        else:
            bounds = bbox

        window = window_from_bounds(*bounds, transform=src.transform)
        window = window.intersection(
            rasterio.windows.Window(0, 0, src.width, src.height),
        )
        if window.width < 1 or window.height < 1:
            return (np.array([]), src.transform, raster_crs)

        data = src.read(1, window=window)
        transform = src.window_transform(window)
    return (data, transform, raster_crs)


# ---------------------------------------------------------------------------
# STAC search
# ---------------------------------------------------------------------------

def search_3dep_tiles(
    bbox: tuple[float, float, float, float],
    collection: str,
) -> list[Any]:
    """Search Planetary Computer for 3DEP tiles covering a bounding box.

    Returns signed pystac Items ready for rasterio access.
    """
    catalog = pystac_client.Client.open(STAC_API_URL)
    search = catalog.search(
        collections=[collection],
        bbox=bbox,
        limit=100,
    )
    items = list(search.items())
    for item in items:
        planetary_computer.sign_inplace(item)
    logger.info(
        "Found %d 3DEP %s tiles for bbox %s",
        len(items), collection, bbox,
    )
    return items


# ---------------------------------------------------------------------------
# Canopy statistics computation
# ---------------------------------------------------------------------------

def compute_canopy_stats(
    chm: np.ndarray,
) -> dict[str, float | None]:
    """Compute canopy height statistics from a clipped CHM array.

    Args:
        chm: 2D numpy array of canopy heights (metres). May contain NaN.

    Returns:
        Dict with keys: mean_height_m, max_height_m, p95_height_m,
        canopy_cover_pct, height_std_dev. Values are None if no valid pixels.
    """
    valid = chm[np.isfinite(chm)]
    # Only consider positive heights (ground = 0, below-ground = noise)
    positive = valid[valid > 0]

    if positive.size == 0:
        return {
            "mean_height_m": None,
            "max_height_m": None,
            "p95_height_m": None,
            "canopy_cover_pct": 0.0,
            "height_std_dev": None,
        }

    canopy_pixels = positive[positive >= CANOPY_HEIGHT_THRESHOLD]
    cover_pct = (canopy_pixels.size / valid.size * 100) if valid.size > 0 else 0.0

    return {
        "mean_height_m": round(float(np.mean(positive)), 2),
        "max_height_m": round(float(np.max(positive)), 2),
        "p95_height_m": round(float(np.percentile(positive, 95)), 2),
        "canopy_cover_pct": round(float(cover_pct), 2),
        "height_std_dev": round(float(np.std(positive)), 2),
    }


def clip_chm_to_buffer(
    chm: np.ndarray,
    transform: rasterio.Affine,
    raster_crs: str,
    buffer_geom: Any,
    buffer_crs: str = STORAGE_CRS,
) -> np.ndarray:
    """Clip a CHM raster to a buffer geometry and return masked array."""
    if buffer_crs.upper() != raster_crs.upper():
        buffer_geom = _reproject_geometry(buffer_geom, buffer_crs, raster_crs)

    if chm.size == 0:
        return np.array([])

    mask = geometry_mask(
        [mapping(buffer_geom)],
        out_shape=chm.shape,
        transform=transform,
        invert=True,
    )
    clipped = np.where(mask, chm, np.nan)
    return clipped


# ---------------------------------------------------------------------------
# Processor class
# ---------------------------------------------------------------------------

class LidarProcessor:
    """Processes USGS 3DEP LiDAR data for riparian buffer canopy analysis.

    Workflow:
        1. Search Planetary Computer for DSM and DTM tiles covering watershed
        2. Read raster windows covering the watershed bounding box
        3. Compute CHM = DSM - DTM
        4. For each buffer, clip CHM and compute canopy statistics
        5. Write results to silver.buffer_canopy
    """

    _UPSERT_SQL = text("""
        INSERT INTO silver.buffer_canopy
            (buffer_id, mean_height_m, max_height_m, p95_height_m,
             canopy_cover_pct, height_std_dev)
        VALUES
            (:buffer_id, :mean_height_m, :max_height_m, :p95_height_m,
             :canopy_cover_pct, :height_std_dev)
        ON CONFLICT (buffer_id) DO UPDATE SET
            mean_height_m    = EXCLUDED.mean_height_m,
            max_height_m     = EXCLUDED.max_height_m,
            p95_height_m     = EXCLUDED.p95_height_m,
            canopy_cover_pct = EXCLUDED.canopy_cover_pct,
            height_std_dev   = EXCLUDED.height_std_dev,
            processed_at     = now()
    """)

    _BUFFERS_SQL = text("""
        SELECT rb.id AS buffer_id,
               ST_AsText(rb.geom) AS geom_wkt,
               ST_XMin(rb.geom) AS xmin,
               ST_YMin(rb.geom) AS ymin,
               ST_XMax(rb.geom) AS xmax,
               ST_YMax(rb.geom) AS ymax
        FROM silver.riparian_buffers rb
        ORDER BY rb.id
    """)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def process(
        self,
        watershed_bbox: tuple[float, float, float, float],
    ) -> int:
        """Run the full LiDAR canopy analysis pipeline.

        Args:
            watershed_bbox: (minx, miny, maxx, maxy) in EPSG:4269.

        Returns:
            Number of buffers processed.
        """
        logger.info("Starting 3DEP LiDAR canopy processing")

        # 1. Search for DSM and DTM tiles
        dsm_items = search_3dep_tiles(watershed_bbox, DSM_COLLECTION)
        dtm_items = search_3dep_tiles(watershed_bbox, DTM_COLLECTION)

        if not dsm_items or not dtm_items:
            logger.warning(
                "No 3DEP tiles found (DSM: %d, DTM: %d). "
                "LiDAR canopy processing skipped.",
                len(dsm_items), len(dtm_items),
            )
            return 0

        # 2. Load buffers from the database
        buffers = self._load_buffers()
        if not buffers:
            logger.warning("No riparian buffers found for canopy analysis")
            return 0

        # 3. Process each buffer against all available tiles
        results = []
        for buf in buffers:
            stats = self._process_buffer(buf, dsm_items, dtm_items)
            if stats:
                results.append(stats)

        # 4. Write results
        if results:
            self._write_results(results)

        logger.info(
            "3DEP LiDAR canopy processing complete: %d/%d buffers scored",
            len(results), len(buffers),
        )
        return len(results)

    def _load_buffers(self) -> list[dict[str, Any]]:
        """Load riparian buffers with their geometries and bboxes."""
        from shapely import wkt

        with self._engine.connect() as conn:
            rows = conn.execute(self._BUFFERS_SQL).fetchall()

        buffers = []
        for row in rows:
            geom = wkt.loads(row.geom_wkt)
            buffers.append({
                "buffer_id": row.buffer_id,
                "geom": geom,
                "bbox": (row.xmin, row.ymin, row.xmax, row.ymax),
            })
        return buffers

    def _process_buffer(
        self,
        buf: dict[str, Any],
        dsm_items: list[Any],
        dtm_items: list[Any],
    ) -> dict[str, Any] | None:
        """Process a single buffer against available 3DEP tiles.

        For each tile pair (DSM + DTM), compute CHM, clip to buffer,
        and compute statistics. Returns the best result (most pixels).
        """
        buffer_id = buf["buffer_id"]
        buffer_geom = buf["geom"]
        buffer_bbox = buf["bbox"]

        best_stats: dict[str, Any] | None = None
        best_pixels = 0

        for dsm_item in dsm_items:
            # Check if DSM tile intersects buffer bbox
            dsm_bbox = dsm_item.bbox
            if not self._bbox_intersects(buffer_bbox, dsm_bbox):
                continue

            # Find matching DTM tile (same spatial extent)
            dtm_item = self._find_matching_dtm(dsm_item, dtm_items)
            if not dtm_item:
                continue

            try:
                # Read DSM and DTM windows for buffer bbox
                dsm_href = self._get_data_href(dsm_item)
                dtm_href = self._get_data_href(dtm_item)
                if not dsm_href or not dtm_href:
                    continue

                dsm_data, dsm_transform, dsm_crs = _read_raster_window(
                    dsm_href, buffer_bbox,
                )
                dtm_data, dtm_transform, dtm_crs = _read_raster_window(
                    dtm_href, buffer_bbox,
                )

                if dsm_data.size == 0 or dtm_data.size == 0:
                    continue

                # DSM and DTM are separate STAC assets that can have different native
                # resolutions and grid origins (3dep-lidar-dtm-native), so cropping both
                # to min(rows, cols) and subtracting would difference misaligned ground
                # pixels. Resample the DTM onto the DSM's exact grid first, then CHM =
                # DSM - DTM is a per-pixel canopy height.
                dsm_clip = dsm_data.astype(np.float32)
                dtm_aligned = np.empty_like(dsm_clip)
                reproject(
                    source=dtm_data.astype(np.float32),
                    destination=dtm_aligned,
                    src_transform=dtm_transform,
                    src_crs=dtm_crs,
                    dst_transform=dsm_transform,
                    dst_crs=dsm_crs,
                    resampling=Resampling.bilinear,
                )

                # Compute CHM
                chm = dsm_clip - dtm_aligned
                # Remove unrealistic values (noise)
                chm[chm < 0] = 0
                chm[chm > 100] = np.nan  # >100m is LiDAR noise

                # Clip to buffer
                clipped = clip_chm_to_buffer(
                    chm, dsm_transform, dsm_crs, buffer_geom,
                )

                valid_count = np.count_nonzero(np.isfinite(clipped))
                if valid_count > best_pixels:
                    stats = compute_canopy_stats(clipped)
                    stats["buffer_id"] = buffer_id
                    best_stats = stats
                    best_pixels = valid_count

            except Exception:
                logger.debug(
                    "Failed to process 3DEP tile for buffer %d",
                    buffer_id,
                    exc_info=True,
                )
                continue

        return best_stats

    @staticmethod
    def _bbox_intersects(
        bbox_a: tuple[float, float, float, float],
        bbox_b: tuple[float, float, float, float] | list[float],
    ) -> bool:
        """Check if two bounding boxes intersect."""
        return not (
            bbox_a[2] < bbox_b[0]  # a right < b left
            or bbox_a[0] > bbox_b[2]  # a left > b right
            or bbox_a[3] < bbox_b[1]  # a top < b bottom
            or bbox_a[1] > bbox_b[3]  # a bottom > b top
        )

    @staticmethod
    def _find_matching_dtm(
        dsm_item: Any,
        dtm_items: list[Any],
    ) -> Any | None:
        """Find a DTM tile that matches a DSM tile's spatial extent."""
        dsm_bbox = dsm_item.bbox
        for dtm_item in dtm_items:
            dtm_bbox = dtm_item.bbox
            # Check for significant overlap (>80% of area)
            overlap_x = max(0, min(dsm_bbox[2], dtm_bbox[2]) - max(dsm_bbox[0], dtm_bbox[0]))
            overlap_y = max(0, min(dsm_bbox[3], dtm_bbox[3]) - max(dsm_bbox[1], dtm_bbox[1]))
            dsm_x = dsm_bbox[2] - dsm_bbox[0]
            dsm_y = dsm_bbox[3] - dsm_bbox[1]
            if dsm_x > 0 and dsm_y > 0:
                overlap_ratio = (overlap_x * overlap_y) / (dsm_x * dsm_y)
                if overlap_ratio > 0.8:
                    return dtm_item
        return None

    @staticmethod
    def _get_data_href(item: Any) -> str | None:
        """Extract the data asset href from a STAC item."""
        # 3DEP items typically have a 'data' asset
        for key in ("data", "elevation", "default"):
            asset = item.assets.get(key)
            if asset:
                return asset.href
        # Fall back to first asset
        if item.assets:
            return next(iter(item.assets.values())).href
        return None

    def _write_results(self, results: list[dict[str, Any]]) -> None:
        """Write canopy statistics to silver.buffer_canopy."""
        with self._engine.connect() as conn:
            conn.execute(self._UPSERT_SQL, results)
            conn.commit()
        logger.info("Wrote %d canopy records to silver.buffer_canopy", len(results))
