"""STAC datacube builder for riparian delineation (Stage 1).

Turns a STAC query over the study-area AOI into an analysis-ready
multitemporal xarray cube. This replaces manual per-scene downloads: the
data-selection step becomes queryable and auditable (AOI + time window +
cloud filter) instead of a manual download mess.

Sources (Microsoft Planetary Computer, a STAC API, free / no key):
- ``sentinel-2-l2a`` — optical, 10-20m, phenology + moisture indices
- ``sentinel-1-rtc``  — C-band SAR backscatter (cloud-independent structure)

Storage CRS is EPSG:4269 (NAD83). Peak growing season for the San Juan
Basin is June-August; dry-season greenness contrast is the phreatophyte
discriminator, so callers typically pass multi-year peak-season windows.

See docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import planetary_computer
import pystac_client
import xarray as xr
from odc.stac import stac_load

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL_2_COLLECTION = "sentinel-2-l2a"
SENTINEL_1_COLLECTION = "sentinel-1-rtc"
WORLDCOVER_COLLECTION = "esa-worldcover"
IO_LULC_COLLECTION = "io-lulc-9-class"
STORAGE_CRS = "EPSG:4269"
MAX_CLOUD_COVER = 20  # percent

# Sentinel-2 L2A bands used for indices + texture. Names as exposed by the
# Planetary Computer STAC assets (not the OlmoEarth band-order convention —
# that reordering happens in delineation_olmoearth.py, not here).
S2_BANDS: tuple[str, ...] = (
    "B02",  # blue
    "B03",  # green
    "B04",  # red
    "B05",  # red-edge 1
    "B06",  # red-edge 2
    "B07",  # red-edge 3
    "B08",  # NIR
    "B8A",  # NIR narrow
    "B11",  # SWIR 1  (moisture)
    "B12",  # SWIR 2  (moisture)
    "B01",  # coastal aerosol (OlmoEarth needs the full 12-band S2 set)
    "B09",  # water vapour
    "SCL",  # scene classification (cloud/shadow mask)
)
S1_BANDS: tuple[str, ...] = ("vv", "vh")

# SCL classes to drop as invalid (cloud, shadow, saturated, no-data, cirrus).
# 0 no-data, 1 saturated, 3 cloud-shadow, 8 cloud-medium, 9 cloud-high,
# 10 thin-cirrus, 11 snow.
SCL_INVALID: frozenset[int] = frozenset({0, 1, 3, 8, 9, 10, 11})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CubeRequest:
    """Immutable description of a datacube to build.

    Attributes:
        bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.
        date_range: STAC datetime range, e.g. ``'2023-06-01/2023-08-31'``.
        resolution_m: Output pixel size in metres (10 for native S2).
        max_cloud_cover: Scene-level cloud-cover ceiling (percent).
    """

    bbox: tuple[float, float, float, float]
    date_range: str
    resolution_m: float = 10.0
    max_cloud_cover: int = MAX_CLOUD_COVER


# ---------------------------------------------------------------------------
# Protocol (interface for dependency injection / testing)
# ---------------------------------------------------------------------------


@runtime_checkable
class StacSearcher(Protocol):
    """Searches a STAC catalog and returns signed items for a collection."""

    def search(
        self,
        collection: str,
        bbox: tuple[float, float, float, float],
        date_range: str,
        query: dict[str, Any] | None,
    ) -> list[Any]:
        """Return signed STAC items matching the criteria."""
        ...


# ---------------------------------------------------------------------------
# Concrete searcher
# ---------------------------------------------------------------------------


class PlanetaryComputerSearcher:
    """Searches Planetary Computer STAC and signs asset URLs in-place."""

    def __init__(self, stac_url: str = STAC_API_URL) -> None:
        self._catalog = pystac_client.Client.open(
            stac_url, modifier=planetary_computer.sign_inplace,
        )

    def search(
        self,
        collection: str,
        bbox: tuple[float, float, float, float],
        date_range: str,
        query: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Search a collection and return signed items.

        Args:
            collection: STAC collection id.
            bbox: ``(minx, miny, maxx, maxy)`` in EPSG:4269.
            date_range: STAC datetime range.
            query: Optional STAC query filter (e.g. cloud cover).

        Returns:
            List of signed pystac Items (possibly empty).
        """
        search = self._catalog.search(
            collections=[collection],
            bbox=bbox,
            datetime=date_range,
            query=query,
        )
        items = list(search.items())
        logger.info(
            "STAC %s: %d items for bbox %s over %s",
            collection, len(items), bbox, date_range,
        )
        return items


# ---------------------------------------------------------------------------
# Cube builders
# ---------------------------------------------------------------------------


def build_sentinel2_cube(
    request: CubeRequest,
    searcher: StacSearcher,
    bands: tuple[str, ...] = S2_BANDS,
) -> xr.Dataset | None:
    """Build a cloud-masked Sentinel-2 datacube for the AOI + time window.

    Loads the requested bands into an xarray Dataset reprojected to the
    storage CRS at the requested resolution, then masks invalid pixels
    (cloud/shadow/snow) using the SCL band.

    Args:
        request: Cube request (bbox, date range, resolution, cloud ceiling).
        searcher: STAC searcher (injected for testability).
        bands: Sentinel-2 asset names to load (must include ``SCL`` to mask).

    Returns:
        An xarray Dataset with dims ``(time, y, x)`` per band, or ``None``
        if no imagery matched the query.
    """
    items = searcher.search(
        SENTINEL_2_COLLECTION,
        request.bbox,
        request.date_range,
        query={"eo:cloud_cover": {"lt": request.max_cloud_cover}},
    )
    if not items:
        logger.warning(
            "No Sentinel-2 imagery for %s over %s",
            request.bbox, request.date_range,
        )
        return None

    cube = stac_load(
        items,
        bands=bands,
        bbox=request.bbox,
        crs=STORAGE_CRS,
        resolution=_deg_resolution(request.resolution_m, request.bbox),
        chunks={},  # dask-backed, lazy until .compute()
        groupby="solar_day",
    )
    _log_cube_shape("Sentinel-2", cube)
    if "SCL" in cube:
        cube = _apply_scl_mask(cube)
    return cube


def build_sentinel1_cube(
    request: CubeRequest,
    searcher: StacSearcher,
    bands: tuple[str, ...] = S1_BANDS,
) -> xr.Dataset | None:
    """Build a Sentinel-1 RTC backscatter datacube for the AOI + time window.

    SAR is cloud-independent, so no cloud filter is applied. Useful for
    structure/moisture sensitivity and for filling optical gaps.

    Args:
        request: Cube request (bbox, date range, resolution).
        searcher: STAC searcher (injected).
        bands: Polarisations to load (``vv``, ``vh``).

    Returns:
        An xarray Dataset with dims ``(time, y, x)``, or ``None`` if empty.
    """
    items = searcher.search(
        SENTINEL_1_COLLECTION, request.bbox, request.date_range, query=None,
    )
    if not items:
        logger.warning(
            "No Sentinel-1 imagery for %s over %s",
            request.bbox, request.date_range,
        )
        return None

    cube = stac_load(
        items,
        bands=bands,
        bbox=request.bbox,
        crs=STORAGE_CRS,
        resolution=_deg_resolution(request.resolution_m, request.bbox),
        chunks={},
        groupby="solar_day",
    )
    _log_cube_shape("Sentinel-1", cube)
    return cube


# ---------------------------------------------------------------------------
# Land-cover grid (weak-label sources, aligned to the S2 grid)
# ---------------------------------------------------------------------------


def build_landcover_grid(
    request: CubeRequest,
    searcher: StacSearcher,
    like: xr.Dataset | None = None,
) -> xr.Dataset | None:
    """Load ESA WorldCover + Impact-Observatory io-lulc onto the S2 grid.

    The most recent year of each is kept. These are the weak-label sources for
    delineation (they replace the retired MRLC/LANDFIRE ArcGIS endpoints).

    When ``like`` is given (the Sentinel-2 cube), the products are loaded onto
    that cube's exact geobox — guaranteeing 1:1 pixel correspondence with the
    feature stack (no off-by-one grid drift between collections). Otherwise they
    are loaded at the request's bbox / CRS / resolution.

    Args:
        request: Cube request (bbox, resolution). Date range is ignored — the
            latest available land-cover year is used.
        searcher: STAC searcher (injected).
        like: Optional reference cube to align the output grid to.

    Returns:
        A 2-D Dataset with ``worldcover`` and ``io_lulc`` variables over
        ``(y, x)``, or ``None`` if neither product is available.
    """
    if like is not None:
        load_kwargs: dict[str, Any] = {"like": like}
    else:
        load_kwargs = {
            "bbox": request.bbox, "crs": STORAGE_CRS,
            "resolution": _deg_resolution(request.resolution_m, request.bbox),
        }

    layers: dict[str, xr.DataArray] = {}
    wc_items = searcher.search(WORLDCOVER_COLLECTION, request.bbox, "2015-01-01/2100-01-01", None)
    if wc_items:
        wc = stac_load(wc_items, bands=["map"], chunks={}, **load_kwargs)
        layers["worldcover"] = _latest_time(wc["map"])

    io_items = searcher.search(IO_LULC_COLLECTION, request.bbox, "2015-01-01/2100-01-01", None)
    if io_items:
        io = stac_load(io_items, bands=["data"], chunks={}, **load_kwargs)
        layers["io_lulc"] = _latest_time(io["data"])

    if not layers:
        logger.warning("No land-cover products for bbox %s", request.bbox)
        return None
    ds = xr.Dataset(layers).compute()
    logger.info("Land-cover grid: %s", list(ds.data_vars))
    return ds


def _latest_time(da: xr.DataArray) -> xr.DataArray:
    """Return the most recent time slice of a land-cover DataArray (2-D)."""
    if "time" in da.dims:
        return da.isel(time=-1, drop=True)
    return da


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


def spatial_dims(cube: xr.Dataset) -> tuple[str, str]:
    """Return the (y, x) spatial dimension names for a cube.

    odc-stac names spatial dims ``latitude``/``longitude`` for geographic
    output CRS (EPSG:4269) and ``y``/``x`` for projected CRS. Downstream
    code should use this instead of hard-coding either pair.

    Args:
        cube: An odc-stac / xarray dataset.

    Returns:
        ``(y_dim, x_dim)`` — e.g. ``('latitude', 'longitude')``.
    """
    if "latitude" in cube.dims:
        return ("latitude", "longitude")
    return ("y", "x")


def _log_cube_shape(label: str, cube: xr.Dataset) -> None:
    """Log timestep count + spatial pixel dims of a cube (dim-name aware)."""
    y_dim, x_dim = spatial_dims(cube)
    logger.info(
        "%s cube: %d timesteps, %d x %d px",
        label,
        cube.sizes.get("time", 0),
        cube.sizes.get(y_dim, 0),
        cube.sizes.get(x_dim, 0),
    )


def _apply_scl_mask(cube: xr.Dataset) -> xr.Dataset:
    """Mask cloud/shadow/snow pixels using the Sentinel-2 SCL band.

    Sets invalid pixels to NaN across all reflectance bands, then drops the
    SCL band from the returned dataset.

    Args:
        cube: Sentinel-2 dataset containing an ``SCL`` variable.

    Returns:
        The masked dataset without the ``SCL`` variable.
    """
    scl = cube["SCL"]
    valid = ~scl.isin(list(SCL_INVALID))
    reflectance = cube.drop_vars("SCL")
    return reflectance.where(valid)


def _deg_resolution(
    resolution_m: float, bbox: tuple[float, float, float, float],
) -> float:
    """Convert a metre resolution to degrees for an EPSG:4269 output grid.

    Uses a latitude-aware approximation (1 degree latitude ~= 111,320 m).
    Longitude degrees shrink with latitude, but for the San Juan Basin
    (~37 N) the latitude-based value is close enough for a target grid;
    odc-stac resamples the source COGs onto it.

    Args:
        resolution_m: Desired pixel size in metres.
        bbox: AOI bbox (used for the centre latitude).

    Returns:
        Pixel size in degrees.
    """
    return resolution_m / 111_320.0
