"""Ingest a deployed riparian-extent probability GeoTIFF into ``silver.riparian_extent``.

Bridges the **DB-free deploy tool** (``deploy_extent_map.py``, per the model-and-inference-hosting
ADR) to the **live map**: the same pooled-RF prediction that produces the static GeoTIFF/GeoJSON
also drives the MapLibre frontend's Stage-1 extent layer (``GET /api/riparian/extent?method=rf``).

Shaping and the ``silver.riparian_extent`` write are **not reimplemented** — this reuses the
canonical ``_vectorize`` + ``_write_extent`` from ``riparian.delineation.runner`` so the polygon
min-mapping-unit filter, per-region mean probability, simplification and the DELETE-then-INSERT
contract stay single-sourced with the in-DB pipeline.

The one impedance mismatch: the deploy GeoTIFF is on a **UTM** grid, but ``_vectorize`` expects a
**degree-space** (EPSG:4269) transform (it simplifies with a per-metre-in-degrees tolerance and the
storage CRS is 4269). So the probability raster is warped to a 4269 grid first, then handed over
unchanged.

Usage (needs the DB up — ``./dev.sh``):
    RIPARIANDB_URI=postgresql://... PYTHONPATH=python-etl \\
        python ingest_extent_to_silver.py --tif .tmp/deploy/riparian_extent_prob.tif
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject
from sqlalchemy import create_engine

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "python-etl"))

from riparian.delineation.runner import _vectorize, _write_extent  # noqa: E402

if TYPE_CHECKING:
    from affine import Affine
    from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ingest_extent")

# Distinct from the in-DB pipeline's 'rf-nmripmap-v1' so the two coexist under method='rf'
# (DELETE is scoped by method + model_version) instead of clobbering each other.
MODEL_VERSION = "rf-nmripmap-4reach-2020"
DST_CRS = "EPSG:4269"
CELL_SIZE_M = 10.0  # native Sentinel-2 pixel — the deploy grid's resolution


@dataclass(frozen=True)
class _ExtentTag:
    """The (method, model_version) pair ``_vectorize``/``_write_extent`` read off a model."""

    method: str
    model_version: str


def _warp_to_4269(tif: Path) -> tuple[np.ndarray, "Affine", int, int]:
    """Warp the UTM probability raster to an EPSG:4269 grid → (prob, transform, h, w)."""
    with rasterio.open(tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, DST_CRS, src.width, src.height, *src.bounds)
        dst = np.full((height, width), np.nan, np.float32)
        reproject(source=rasterio.band(src, 1), destination=dst,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs=DST_CRS,
                  resampling=Resampling.bilinear)
    return dst, transform, height, width


def _engine() -> "Engine":
    """SQLAlchemy engine from the Aspire-injected DSN (RIPARIANDB_URI / DATABASE_URL)."""
    url = os.environ.get("RIPARIANDB_URI") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set RIPARIANDB_URI (or DATABASE_URL) to the PostGIS DSN — is ./dev.sh up?")
    return create_engine(url)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tif", type=Path, default=HERE / ".tmp/deploy/riparian_extent_prob.tif",
                    help="deploy probability GeoTIFF (UTM)")
    ap.add_argument("--threshold", type=float, default=0.5, help="riparian probability cut")
    ap.add_argument("--model-version", default=MODEL_VERSION, help="version tag written to silver")
    a = ap.parse_args()

    prob, transform, _, _ = _warp_to_4269(a.tif)
    filled = np.nan_to_num(prob)
    tag = _ExtentTag("rf", a.model_version)
    rows = _vectorize(filled >= a.threshold, filled, transform, tag, CELL_SIZE_M, None)
    n = _write_extent(_engine(), rows, tag, None)
    logger.info("ingested %d riparian polygons → silver.riparian_extent (method=rf, version=%s)",
                n, a.model_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
