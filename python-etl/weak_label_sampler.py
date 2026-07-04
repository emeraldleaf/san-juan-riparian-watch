"""Weak-label sampler for riparian delineation (Stage 1b).

Builds riparian / not-riparian training labels from the *agreement* of two
independent land-cover products loaded on the Sentinel-2 grid via STAC — ESA
WorldCover and Impact-Observatory io-lulc — plus optional NWI wetlands. No field
data (the honest ceiling on "reliable"; Pace et al. 2022 note the need for local
calibration).

Why not wetland classes alone? In the semi-arid San Juan Basin there is
effectively no herbaceous-wetland / flooded-vegetation land cover — riparian is
**woody vegetation (tree/shrub) growing near water**, not wetland. So the label
is: *woody cover within ~100 m of water* (from either product), OR a wetland
class where one exists. The two products disagree substantially over upland, so
their agreement on woody-near-water is a high-precision positive signal.

Labelling rule (kept high-precision on purpose):
- **Positive** where ≥1 product flags woody-near-water or wetland; ``agreement``
  (0–3 incl. NWI) records confidence.
- **Negative** where clearly-upland (built / bare / crop / grass / rangeland)
  AND far (>200 m) from water AND not positive.
- **Excluded** otherwise (ambiguous — not used for training).

Labels come out on the same grid as the feature stack, so they align 1:1 with
the feature matrix. Storage CRS is EPSG:4269. See
docs/specs/2026-07-03-stage1-riparian-delineation.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import xarray as xr
from scipy import ndimage
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from stac_datacube import spatial_dims

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Land-cover class constants
# ---------------------------------------------------------------------------

# ESA WorldCover: 10 tree, 20 shrub, 30 grass, 40 crop, 50 built, 60 bare,
# 70 snow, 80 water, 90 herbaceous wetland, 95 mangrove, 100 moss/lichen.
WC_WOODY: frozenset[int] = frozenset({10, 20})
WC_WATER: frozenset[int] = frozenset({80})
WC_WETLAND: frozenset[int] = frozenset({90, 95})
WC_UPLAND: frozenset[int] = frozenset({30, 40, 50, 60, 70, 100})

# io-lulc-9-class: 1 water, 2 trees, 4 flooded veg, 5 crops, 7 built, 8 bare,
# 9 snow, 10 clouds, 11 rangeland.
IO_WOODY: frozenset[int] = frozenset({2})
IO_WATER: frozenset[int] = frozenset({1})
IO_WETLAND: frozenset[int] = frozenset({4})
IO_UPLAND: frozenset[int] = frozenset({5, 7, 8, 9, 11})

NEAR_WATER_M = 100.0   # woody within this distance of water → riparian candidate
FAR_WATER_M = 200.0    # upland must be beyond this to be a confident negative
LABEL_SOURCE = "worldcover+io_lulc+nwi:agreement"

LABEL_EXCLUDE = -1
LABEL_NEGATIVE = 0
LABEL_POSITIVE = 1


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelGrid:
    """Per-pixel weak labels aligned to the Sentinel-2 grid.

    Attributes:
        label: ``(y, x)`` int8 — 1 riparian, 0 not, -1 exclude from training.
        agreement: ``(y, x)`` int8 — number of sources (0–3) voting riparian.
        wc_hit: ``(y, x)`` bool — WorldCover voted riparian.
        io_hit: ``(y, x)`` bool — io-lulc voted riparian.
        nwi_hit: ``(y, x)`` bool — NWI voted riparian.
        y_coords: latitude coordinate values (length y).
        x_coords: longitude coordinate values (length x).
    """

    label: np.ndarray
    agreement: np.ndarray
    wc_hit: np.ndarray
    io_hit: np.ndarray
    nwi_hit: np.ndarray
    y_coords: np.ndarray
    x_coords: np.ndarray


@dataclass(frozen=True)
class WeakLabelSample:
    """A single weak-labeled grid point (for DB persistence / reproducibility)."""

    lat: float
    lon: float
    label: bool
    landfire_hit: bool  # retained column name = "worldcover" vote in this schema
    nlcd_hit: bool      # retained column name = "io_lulc" vote in this schema
    nwi_hit: bool
    agreement_count: int


# ---------------------------------------------------------------------------
# Pure label logic
# ---------------------------------------------------------------------------


def _isin(arr: np.ndarray | None, classes: frozenset[int], shape: tuple[int, int]) -> np.ndarray:
    """Boolean membership test, tolerant of a missing (None) product."""
    if arr is None:
        return np.zeros(shape, dtype=bool)
    return np.isin(arr.astype(np.int64), list(classes))


def near_water_mask(water: np.ndarray, resolution_m: float, dist_m: float) -> np.ndarray:
    """Boolean mask of pixels within ``dist_m`` of any water pixel.

    Uses a Euclidean distance transform on the complement of the water mask.

    Args:
        water: ``(y, x)`` bool water mask.
        resolution_m: Pixel size in metres.
        dist_m: Proximity threshold in metres.

    Returns:
        ``(y, x)`` bool mask.
    """
    if not water.any():
        return np.zeros(water.shape, dtype=bool)
    dist_px = ndimage.distance_transform_edt(~water)
    return (dist_px * resolution_m) <= dist_m


def build_weak_label_grid(
    landcover: xr.Dataset,
    resolution_m: float,
    nwi_mask: np.ndarray | None = None,
) -> LabelGrid:
    """Compute the weak-label grid from aligned land-cover products.

    Args:
        landcover: Dataset from ``stac_datacube.build_landcover_grid`` with
            ``worldcover`` and/or ``io_lulc`` 2-D variables.
        resolution_m: Grid pixel size in metres.
        nwi_mask: Optional ``(y, x)`` bool mask of NWI wetland presence.

    Returns:
        A :class:`LabelGrid`.
    """
    y_dim, x_dim = spatial_dims(landcover)
    wc = landcover["worldcover"].values if "worldcover" in landcover else None
    io = landcover["io_lulc"].values if "io_lulc" in landcover else None
    ref = wc if wc is not None else io
    if ref is None:
        raise ValueError("landcover has neither worldcover nor io_lulc")
    shape = ref.shape

    water = _isin(wc, WC_WATER, shape) | _isin(io, IO_WATER, shape)
    near = near_water_mask(water, resolution_m, NEAR_WATER_M)
    far = ~near_water_mask(water, resolution_m, FAR_WATER_M)

    wc_hit = (_isin(wc, WC_WOODY, shape) & near) | _isin(wc, WC_WETLAND, shape)
    io_hit = (_isin(io, IO_WOODY, shape) & near) | _isin(io, IO_WETLAND, shape)
    nwi_hit = nwi_mask if nwi_mask is not None else np.zeros(shape, dtype=bool)

    agreement = wc_hit.astype(np.int8) + io_hit.astype(np.int8) + nwi_hit.astype(np.int8)
    positive = agreement >= 1
    upland = _isin(wc, WC_UPLAND, shape) | _isin(io, IO_UPLAND, shape)
    negative = (~positive) & upland & far

    label = np.full(shape, LABEL_EXCLUDE, dtype=np.int8)
    label[negative] = LABEL_NEGATIVE
    label[positive] = LABEL_POSITIVE

    logger.info(
        "Weak-label grid: %d riparian, %d not, %d excluded (%d px)",
        int(positive.sum()), int(negative.sum()),
        int((label == LABEL_EXCLUDE).sum()), label.size,
    )
    return LabelGrid(
        label=label, agreement=agreement, wc_hit=wc_hit, io_hit=io_hit,
        nwi_hit=nwi_hit,
        y_coords=landcover[y_dim].values, x_coords=landcover[x_dim].values,
    )


def labels_for_pixels(grid: LabelGrid, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract labeled training pixels intersected with a feature-valid mask.

    Args:
        grid: The weak-label grid.
        valid_mask: ``(y, x)`` bool mask of pixels with complete features
            (from ``FeatureStack.valid_mask``); must match the grid shape.

    Returns:
        ``(row_index, labels, latlon)`` where ``row_index`` selects the rows of
        a feature matrix built from the same ``valid_mask`` (row-major over
        valid cells), ``labels`` are the 0/1 labels, and ``latlon`` is an
        ``(n, 2)`` array of (lat, lon) for spatial CV.
    """
    if valid_mask.shape != grid.label.shape:
        raise ValueError("valid_mask and label grid shapes differ")
    trainable = valid_mask & (grid.label != LABEL_EXCLUDE)
    # Row index into the feature matrix (valid cells in row-major order).
    feat_row = np.cumsum(valid_mask.ravel()) - 1
    flat_train = trainable.ravel()
    row_index = feat_row[flat_train]

    labels = grid.label.ravel()[flat_train].astype(int)
    yy, xx = np.meshgrid(grid.y_coords, grid.x_coords, indexing="ij")
    latlon = np.column_stack([yy.ravel()[flat_train], xx.ravel()[flat_train]])
    return row_index, labels, latlon


def grid_to_samples(grid: LabelGrid) -> list[WeakLabelSample]:
    """Flatten definite-label grid cells to WeakLabelSample points for the DB."""
    yy, xx = np.meshgrid(grid.y_coords, grid.x_coords, indexing="ij")
    keep = grid.label != LABEL_EXCLUDE
    samples: list[WeakLabelSample] = []
    for lat, lon, lab, ag, wc, io, nwi in zip(
        yy[keep], xx[keep], grid.label[keep], grid.agreement[keep],
        grid.wc_hit[keep], grid.io_hit[keep], grid.nwi_hit[keep],
    ):
        samples.append(
            WeakLabelSample(
                lat=float(lat), lon=float(lon), label=bool(lab == LABEL_POSITIVE),
                landfire_hit=bool(wc), nlcd_hit=bool(io), nwi_hit=bool(nwi),
                agreement_count=int(ag),
            )
        )
    return samples


# ---------------------------------------------------------------------------
# NWI (optional third vote) — rasterized to the grid
# ---------------------------------------------------------------------------


def load_nwi_mask(
    engine: Engine, grid_like: LabelGrid, bbox: tuple[float, float, float, float],
) -> np.ndarray | None:
    """Rasterize NWI wetland polygons (bronze) onto the label grid.

    Args:
        engine: SQLAlchemy engine.
        grid_like: A LabelGrid providing the target grid coordinates.
        bbox: AOI ``(minx, miny, maxx, maxy)`` in EPSG:4269.

    Returns:
        ``(y, x)`` bool mask, or None if NWI is unavailable.
    """
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    from shapely import wkb

    # Parameterized SQLAlchemy + WKB → shapely (avoids a geopandas read_postgis
    # params quirk under pandas 3 that silently dropped the NWI vote).
    sql = text(
        "SELECT ST_AsBinary(geom) AS wkb FROM bronze.nwi_wetlands "
        "WHERE geom && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4269)"
    )
    params = {"minx": bbox[0], "miny": bbox[1], "maxx": bbox[2], "maxy": bbox[3]}
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Could not load NWI wetlands: %s", exc)
        return None
    geoms = [wkb.loads(bytes(r[0])) for r in rows if r[0] is not None]
    if not geoms:
        return None

    h, w = grid_like.label.shape
    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], w, h)
    mask = rasterize(
        ((geom, 1) for geom in geoms),
        out_shape=(h, w), transform=transform, fill=0, dtype="uint8",
    )
    return mask.astype(bool)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class PostGISWeakLabelWriter:
    """Writes weak-labeled samples to bronze.riparian_training_samples."""

    _INSERT_SQL = text("""
        INSERT INTO bronze.riparian_training_samples
            (label, label_source, landfire_hit, nlcd_hit, nwi_hit,
             agreement_count, huc12, geom)
        VALUES
            (:label, :label_source, :landfire_hit, :nlcd_hit, :nwi_hit,
             :agreement_count, :huc12, ST_SetSRID(ST_MakePoint(:lon, :lat), 4269))
    """)

    _DELETE_HUC12 = text(
        "DELETE FROM bronze.riparian_training_samples WHERE huc12 = :huc12"
    )

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_samples(
        self, samples: list[WeakLabelSample], huc12: str | None = None,
    ) -> int:
        """Batch-insert samples; returns the count written.

        When ``huc12`` is given, existing samples for that tile are deleted
        first so re-runs are idempotent per subwatershed.
        """
        if not samples:
            return 0
        params = [
            {
                "label": s.label, "label_source": LABEL_SOURCE,
                "landfire_hit": s.landfire_hit, "nlcd_hit": s.nlcd_hit,
                "nwi_hit": s.nwi_hit, "agreement_count": s.agreement_count,
                "huc12": huc12, "lon": s.lon, "lat": s.lat,
            }
            for s in samples
        ]
        with self._engine.connect() as conn:
            if huc12 is not None:
                conn.execute(self._DELETE_HUC12, {"huc12": huc12})
            conn.execute(self._INSERT_SQL, params)
            conn.commit()
        return len(samples)
