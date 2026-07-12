"""Raster processing framework for categorical and continuous rasters.

Provides protocols and concrete implementations for fetching raster data
from ArcGIS ImageServer and OGC WCS endpoints, plus zonal statistics
functions for extracting per-buffer metrics from rasters.

Generalizes the rasterio clipping/masking pattern from ndvi_processor.py
into a reusable framework for NLCD, LANDFIRE, and future raster datasets.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.windows
import requests
from pyproj import Transformer
from rasterio.features import geometry_mask
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STORAGE_CRS = "EPSG:4269"
DEFAULT_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RasterResult:
    """Immutable container for raster data read from a remote source.

    Attributes:
        data: 2D numpy array of raster values.
        transform: Affine transform mapping pixel coords to CRS coords.
        crs: Coordinate reference system string (e.g., ``'EPSG:4269'``).
        nodata: NoData sentinel value, or None if not applicable.
    """

    data: np.ndarray
    transform: rasterio.Affine
    crs: str
    nodata: float | None = None


@dataclass(frozen=True)
class CategoricalStats:
    """Per-buffer categorical raster statistics.

    Attributes:
        buffer_id: Buffer primary key.
        class_counts: Mapping of raster class value → pixel count.
        total_pixels: Total valid pixels in buffer.
    """

    buffer_id: int
    class_counts: dict[int, int]
    total_pixels: int


@dataclass(frozen=True)
class ContinuousStats:
    """Per-buffer continuous raster statistics.

    Attributes:
        buffer_id: Buffer primary key.
        mean: Mean raster value within buffer.
        min_val: Minimum raster value within buffer.
        max_val: Maximum raster value within buffer.
        std_dev: Standard deviation of values.
        pixel_count: Number of valid pixels.
    """

    buffer_id: int
    mean: float
    min_val: float
    max_val: float
    std_dev: float
    pixel_count: int


# ---------------------------------------------------------------------------
# Protocols (interfaces for dependency injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class RasterSource(Protocol):
    """Provides raster data for a given bounding box."""

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Fetch raster data clipped to the given bounding box.

        Args:
            bbox: ``(minx, miny, maxx, maxy)`` in STORAGE_CRS.

        Returns:
            RasterResult with clipped data, transform, and CRS.
        """
        ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class ImageServerSource:
    """Fetches raster data from an ArcGIS ImageServer ``exportImage`` endpoint.

    Suitable for LANDFIRE and other ESRI-hosted raster services.

    The endpoint returns a GeoTIFF which is read in memory via
    ``rasterio.MemoryFile``.

    Args:
        base_url: Base ImageServer URL (e.g.,
            ``https://lfps.usgs.gov/.../US_250EVT/ImageServer``).
        pixel_size: Output pixel size in CRS units (default 30m ≈ 0.00028°).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        pixel_size: float = 0.00028,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._pixel_size = pixel_size
        self._timeout = timeout
        self._session = requests.Session()

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Fetch raster data from ImageServer for the given bounding box.

        Uses the ``exportImage`` REST operation with GeoTIFF output.

        Args:
            bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.

        Returns:
            RasterResult with data array, affine transform, and CRS.

        Raises:
            requests.HTTPError: If the server responds with an error.
            rasterio.RasterioIOError: If the response is not valid raster data.
        """
        minx, miny, maxx, maxy = bbox
        width = max(1, int((maxx - minx) / self._pixel_size))
        height = max(1, int((maxy - miny) / self._pixel_size))

        # Cap at reasonable size to avoid memory issues
        max_dim = 4096
        if width > max_dim or height > max_dim:
            scale = max_dim / max(width, height)
            width = int(width * scale)
            height = int(height * scale)

        params: dict[str, Any] = {
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bboxSR": "4269",
            "imageSR": "4269",
            "size": f"{width},{height}",
            "format": "tiff",
            "f": "image",
            "noData": "",
            "interpolation": "RSP_NearestNeighbor",
        }

        url = f"{self._base_url}/exportImage"
        logger.info(
            "Fetching raster from ImageServer: %s (%dx%d pixels)",
            self._base_url.split("/")[-2], width, height,
        )

        response = self._session.get(
            url, params=params, timeout=self._timeout,
        )
        response.raise_for_status()

        # Check for JSON error response (ImageServer returns JSON on errors)
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type or "html" in content_type:
            logger.error(
                "ImageServer returned non-image response: %s",
                response.text[:500],
            )
            raise ValueError(
                f"ImageServer did not return image data: {response.text[:200]}"
            )

        return self._read_tiff_bytes(response.content)

    @staticmethod
    def _read_tiff_bytes(data: bytes) -> RasterResult:
        """Parse GeoTIFF bytes into a RasterResult."""
        with rasterio.MemoryFile(data) as memfile:
            with memfile.open() as src:
                arr = src.read(1)
                transform = src.transform
                crs = str(src.crs)
                nodata = src.nodata
        return RasterResult(
            data=arr,
            transform=transform,
            crs=crs,
            nodata=float(nodata) if nodata is not None else None,
        )


class WCSSource:
    """Fetches raster data from an OGC WCS 2.0 service.

    Suitable for NLCD from MRLC and other OGC-compliant services.

    Args:
        base_url: WCS service base URL.
        coverage_id: Coverage identifier (e.g.,
            ``'NLCD_2021_Land_Cover_L48'``).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        coverage_id: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._coverage_id = coverage_id
        self._timeout = timeout
        self._session = requests.Session()

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Fetch raster data from WCS for the given bounding box.

        Uses WCS 2.0.1 ``GetCoverage`` operation with subsetting.

        Args:
            bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.

        Returns:
            RasterResult with data array, affine transform, and CRS.

        Raises:
            requests.HTTPError: If the server responds with an error.
        """
        minx, miny, maxx, maxy = bbox

        params: dict[str, Any] = {
            "service": "WCS",
            "version": "2.0.1",
            "request": "GetCoverage",
            "coverageId": self._coverage_id,
            "subset": [
                f"Long({minx},{maxx})",
                f"Lat({miny},{maxy})",
            ],
            "format": "image/geotiff",
        }

        logger.info(
            "Fetching raster from WCS: %s (coverage %s)",
            self._base_url, self._coverage_id,
        )

        response = self._session.get(
            self._base_url, params=params, timeout=self._timeout,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "xml" in content_type.lower():
            logger.error(
                "WCS returned XML error: %s", response.text[:500],
            )
            raise ValueError(
                f"WCS service returned error: {response.text[:200]}"
            )

        return ImageServerSource._read_tiff_bytes(response.content)


class GeoServerWmsSource:
    """Fetches raster data from an OGC WMS GetMap endpoint as GeoTIFF.

    Suitable for MRLC GeoServer and other WMS services that support
    GeoTIFF output format.  WMS renders a styled image, so paletted
    TIFFs use sequential palette indices instead of the original raster
    values.  An optional ``palette_to_value`` mapping re-codes the pixel
    values back to the real categorical codes (e.g. NLCD class codes).

    Args:
        base_url: WMS endpoint URL (e.g.,
            ``'https://www.mrlc.gov/geoserver/mrlc_display/ows'``).
        layers: WMS layer name(s).
        palette_to_value: Optional mapping from palette index to real
            class code.  When provided, pixel values in the returned
            raster are remapped.
        target_crs: Target CRS for the output raster.
        pixel_size: Output pixel size in CRS units.
        timeout: HTTP request timeout in seconds.
    """

    # MRLC GeoServer native CRS is EPSG:3857 — request in that CRS
    _NATIVE_CRS = "EPSG:3857"

    # MRLC NLCD WMS palette index → standard NLCD Anderson Level II code.
    # Derived by matching MRLC GeoServer palette RGB values to official
    # NLCD colour table (USGS SIR 2019-5001).
    NLCD_PALETTE_MAP: dict[int, int] = {
        0: 0,     # transparent / nodata
        1: 11,    # Open Water
        2: 12,    # Perennial Ice/Snow
        3: 21,    # Developed, Open Space
        4: 22,    # Developed, Low Intensity
        5: 23,    # Developed, Medium Intensity
        6: 24,    # Developed, High Intensity
        7: 31,    # Barren Land
        8: 0,     # unassigned / nodata
        9: 41,    # Deciduous Forest
        10: 42,   # Evergreen Forest
        11: 43,   # Mixed Forest
        12: 51,   # Dwarf Scrub (Alaska)
        13: 52,   # Shrub/Scrub
        14: 71,   # Grassland/Herbaceous
        15: 72,   # Sedge/Herbaceous (Alaska)
        16: 73,   # Lichens (Alaska)
        17: 74,   # Moss (Alaska)
        18: 81,   # Pasture/Hay
        19: 82,   # Cultivated Crops
        20: 90,   # Woody Wetlands
        21: 95,   # Emergent Herbaceous Wetlands
    }

    def __init__(
        self,
        base_url: str,
        layers: str,
        palette_to_value: dict[int, int] | None = None,
        target_crs: str = STORAGE_CRS,
        pixel_size: float = 30.0,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._layers = layers
        self._palette_map = palette_to_value
        self._target_crs = target_crs
        self._pixel_size = pixel_size
        self._timeout = timeout
        self._session = requests.Session()
        self._transformer = Transformer.from_crs(
            "EPSG:4269", self._NATIVE_CRS, always_xy=True,
        )

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Fetch raster from WMS GetMap as GeoTIFF.

        Args:
            bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.

        Returns:
            RasterResult with data array, affine transform, and CRS.
        """
        minx, miny, maxx, maxy = bbox

        # Project bbox to native CRS (EPSG:3857)
        x0, y0 = self._transformer.transform(minx, miny)
        x1, y1 = self._transformer.transform(maxx, maxy)

        width = max(1, int(abs(x1 - x0) / self._pixel_size))
        height = max(1, int(abs(y1 - y0) / self._pixel_size))
        max_dim = 4096
        if width > max_dim or height > max_dim:
            scale = max_dim / max(width, height)
            width = int(width * scale)
            height = int(height * scale)

        params: dict[str, Any] = {
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetMap",
            "layers": self._layers,
            "srs": self._NATIVE_CRS,
            "bbox": f"{x0},{y0},{x1},{y1}",
            "width": str(width),
            "height": str(height),
            "format": "image/geotiff",
            "styles": "",
        }

        logger.info(
            "Fetching raster from WMS: %s (%dx%d pixels)",
            self._layers, width, height,
        )

        response = self._session.get(
            self._base_url, params=params, timeout=self._timeout,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "xml" in content_type.lower() or "html" in content_type.lower():
            logger.error(
                "WMS returned non-image response: %s", response.text[:500],
            )
            raise ValueError(
                f"WMS did not return image data: {response.text[:200]}"
            )

        return self._remap_palette(
            ImageServerSource._read_tiff_bytes(response.content)
        )

    # ------------------------------------------------------------------
    def _remap_palette(self, result: RasterResult) -> RasterResult:
        """Remap palette indices to real class codes if a map is set."""
        if self._palette_map is None:
            return result

        lookup = np.zeros(256, dtype=np.uint8)
        for idx, code in self._palette_map.items():
            if 0 <= idx < 256:
                lookup[idx] = code

        remapped = lookup[result.data]
        logger.info(
            "Remapped %d palette indices to class codes",
            int(np.count_nonzero(remapped)),
        )
        return RasterResult(
            data=remapped,
            transform=result.transform,
            crs=result.crs,
            nodata=result.nodata,
        )

class FallbackRasterSource:
    """Tries a primary RasterSource, falls back to a secondary on failure.

    Args:
        primary: Primary raster source (tried first).
        fallback: Fallback raster source (used if primary fails).
    """

    def __init__(
        self, primary: RasterSource, fallback: RasterSource,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Fetch from primary; on failure, try fallback."""
        try:
            return self._primary.fetch(bbox)
        except Exception:
            logger.warning(
                "Primary raster source failed — trying fallback",
                exc_info=True,
            )
            return self._fallback.fetch(bbox)


class LocalRasterSource:
    """Reads raster data from a local file path or accessible URL.

    Uses rasterio windowed reads for efficient access to COG files.
    Suitable for pre-downloaded rasters or S3-hosted COGs.

    Args:
        path: File path or URL to the raster (e.g., local GeoTIFF or COG).
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> RasterResult:
        """Read raster data windowed to the given bounding box.

        Args:
            bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.

        Returns:
            RasterResult with windowed data, transform, and CRS.
        """
        from shapely.geometry import box as shapely_box

        logger.info("Reading raster from %s", self._path)

        with rasterio.open(self._path) as src:
            crs = str(src.crs)
            nodata = src.nodata

            # Reproject bbox if raster CRS differs from storage CRS
            if crs.upper() != STORAGE_CRS.upper():
                bbox_geom = shapely_box(*bbox)
                transformer = Transformer.from_crs(
                    STORAGE_CRS, crs, always_xy=True,
                )
                bbox_geom = shapely_transform(transformer.transform, bbox_geom)
                bounds = bbox_geom.bounds
            else:
                bounds = bbox

            window = rasterio.windows.from_bounds(
                *bounds, transform=src.transform,
            )
            window = window.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height),
            )
            data = src.read(1, window=window)
            transform = src.window_transform(window)

        return RasterResult(
            data=data,
            transform=transform,
            crs=crs,
            nodata=float(nodata) if nodata is not None else None,
        )


# ---------------------------------------------------------------------------
# Zonal statistics functions
# ---------------------------------------------------------------------------


def _prepare_transformer(
    raster_crs: str,
) -> Transformer | None:
    """Create a CRS transformer if the raster CRS differs from storage CRS.

    Args:
        raster_crs: CRS string of the raster data.

    Returns:
        Transformer or None if no reprojection is needed.
    """
    if raster_crs.upper() == STORAGE_CRS.upper():
        return None
    return Transformer.from_crs(STORAGE_CRS, raster_crs, always_xy=True)


def _mask_buffer(
    geom: Any,
    data_shape: tuple[int, ...],
    transform: rasterio.Affine,
    transformer: Transformer | None,
) -> np.ndarray | None:
    """Create a boolean mask for a buffer geometry on a raster grid.

    Args:
        geom: Shapely geometry in STORAGE_CRS.
        data_shape: Shape of the raster array ``(rows, cols)``.
        transform: Affine transform of the raster.
        transformer: Optional CRS transformer.

    Returns:
        Boolean mask (True where geometry covers), or None on failure.
    """
    if transformer is not None:
        geom = shapely_transform(transformer.transform, geom)

    try:
        mask = geometry_mask(
            [mapping(geom)],
            out_shape=data_shape,
            transform=transform,
            invert=True,
        )
    except (ValueError, IndexError):
        return None
    return mask


def compute_categorical_zonal_stats(
    raster: RasterResult,
    buffers: gpd.GeoDataFrame,
) -> list[CategoricalStats]:
    """Compute per-buffer pixel counts for each categorical raster class.

    For each buffer geometry, masks the raster and counts occurrences
    of each unique class value within the buffer.

    Args:
        raster: Categorical raster data (e.g., NLCD land cover).
        buffers: GeoDataFrame with ``id`` column and geometry in STORAGE_CRS.

    Returns:
        List of CategoricalStats, one per buffer with data.
    """
    transformer = _prepare_transformer(raster.crs)
    results: list[CategoricalStats] = []

    for _, row in buffers.iterrows():
        mask = _mask_buffer(
            row.geometry, raster.data.shape, raster.transform, transformer,
        )
        if mask is None:
            continue

        pixels = raster.data[mask]
        # Filter out nodata values (guard against a NaN nodata, which int() rejects)
        if raster.nodata is not None and np.isfinite(raster.nodata):
            pixels = pixels[pixels != int(raster.nodata)]
        # Filter out zero (often used as nodata in categorical rasters)
        pixels = pixels[pixels != 0]

        if pixels.size == 0:
            continue

        unique, counts = np.unique(pixels, return_counts=True)
        class_counts = {int(u): int(c) for u, c in zip(unique, counts)}

        results.append(CategoricalStats(
            buffer_id=int(row["id"]),
            class_counts=class_counts,
            total_pixels=int(pixels.size),
        ))

    logger.info(
        "Computed categorical stats for %d of %d buffers",
        len(results), len(buffers),
    )
    return results


def compute_continuous_zonal_stats(
    raster: RasterResult,
    buffers: gpd.GeoDataFrame,
) -> list[ContinuousStats]:
    """Compute per-buffer continuous statistics (mean, min, max, std).

    For each buffer geometry, masks the raster and computes descriptive
    statistics on the valid pixel values within the buffer.

    Args:
        raster: Continuous raster data (e.g., LANDFIRE EVH heights).
        buffers: GeoDataFrame with ``id`` column and geometry in STORAGE_CRS.

    Returns:
        List of ContinuousStats, one per buffer with data.
    """
    transformer = _prepare_transformer(raster.crs)
    results: list[ContinuousStats] = []

    for _, row in buffers.iterrows():
        mask = _mask_buffer(
            row.geometry, raster.data.shape, raster.transform, transformer,
        )
        if mask is None:
            continue

        pixels = raster.data[mask].astype(np.float64)
        # Filter out nodata values
        if raster.nodata is not None:
            pixels = pixels[pixels != raster.nodata]
        # Filter out zero/negative and the 32767 Int16 fill sentinel. LANDFIRE EVH
        # uses 32767 for nodata but does not always declare it in raster.nodata; it
        # is never a valid height, so leaving it in grossly inflates the mean.
        pixels = pixels[(pixels > 0) & (pixels != 32767)]

        if pixels.size == 0:
            continue

        results.append(ContinuousStats(
            buffer_id=int(row["id"]),
            mean=float(np.mean(pixels)),
            min_val=float(np.min(pixels)),
            max_val=float(np.max(pixels)),
            std_dev=float(np.std(pixels)),
            pixel_count=int(pixels.size),
        ))

    logger.info(
        "Computed continuous stats for %d of %d buffers",
        len(results), len(buffers),
    )
    return results
