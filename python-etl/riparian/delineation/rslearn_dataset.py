"""Materialise a local rslearn dataset for the OlmoEarth fine-tune.

Phase 0, step 3 of ``docs/specs/2026-07-12-gpu-finetune-execution-plan.md``. This is **CPU +
network**, not GPU: it downloads Sentinel-2 from Planetary Computer and writes it to disk. Doing it
on a rented GPU would be money set on fire — the card idles while the network works.

What this builds::

    dataset/
        config.json                  <- rslearn reads config.json, NOT dataset.json.
        windows/<group>/<window>/    <- the scaffold's `dataset.json` is the olmoearth_run
            metadata.json               convention; rslearn's own loader wants config.json, and
            layers/                     it will silently find no config if you hand it the other
                label/data.geojson      name. Copy, do not rename in place.
                sentinel2/...

Windows are square, ``WINDOW_PX`` on a side, in the local UTM zone at 10 m — Sentinel-2's native
grid. We tile the AOI and **keep only windows that actually contain riparian label**, because a
window of pure upland teaches the model nothing and still costs a full Sentinel-2 download.

See CLAUDE.md.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

#: Window side in pixels. 32 px x 10 m = 320 m. The corridor is 50-200 m wide, so a window holds
#: riparian AND upland — which is the point of a segmentation task, but see the spec's risk table:
#: if recall collapses, this is the first knob to turn.
WINDOW_PX: Final[int] = 32

#: Sentinel-2 native resolution.
RESOLUTION_M: Final[float] = 10.0

#: Fit on the label's own vintage. NMRipMap v2.0 Plus was photo-interpreted from NAIP 2020.
TIME_RANGE: Final[tuple[datetime, datetime]] = (
    datetime(2020, 6, 1, tzinfo=timezone.utc),
    datetime(2020, 8, 31, tzinfo=timezone.utc),
)

#: A window with no riparian pixels costs a full S2 download and teaches nothing.
MIN_POSITIVE_PX: Final[int] = 1


@dataclass(frozen=True)
class DatasetBuild:
    """What was actually built."""

    path: Path
    n_windows: int
    n_windows_skipped_empty: int


def utm_epsg(lon: float, lat: float) -> int:
    """EPSG code of the UTM zone containing this point."""
    zone = int((lon + 180) / 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def build(
    dest: Path,
    scaffold_config: Path,
    bbox: tuple[float, float, float, float],
    label_fc: dict,
    group: str = "train",
    window_px: int = WINDOW_PX,
) -> DatasetBuild:
    """Create the rslearn dataset directory, windows, and per-window label GeoJSON.

    Args:
        dest: Dataset root to create (destroyed and rebuilt if it exists).
        scaffold_config: The scaffold's ``dataset.json`` — copied to ``config.json``.
        bbox: AOI ``(minx, miny, maxx, maxy)`` in EPSG:4326.
        label_fc: The label FeatureCollection from ``riparian.labels.label_layer``.
        group: rslearn window group name.
        window_px: Window side in pixels.

    Returns:
        What was built.

    Raises:
        ValueError: If no window contains any riparian label — a dataset of pure negatives would
            train happily and learn nothing.
    """
    import shapely
    from rasterio.crs import CRS
    from rslearn.dataset import Dataset, Window
    from rslearn.utils.feature import Feature
    from rslearn.utils.geometry import Projection, STGeometry
    from rslearn.utils.vector_format import GeojsonVectorFormat
    from upath import UPath

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy(scaffold_config, dest / "config.json")

    epsg = utm_epsg((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    projection = Projection(CRS.from_epsg(epsg), RESOLUTION_M, -RESOLUTION_M)
    logger.info("dataset CRS: EPSG:%d at %.0f m", epsg, RESOLUTION_M)

    # Project the AOI and every label polygon into the window projection ONCE.
    wgs84 = Projection(CRS.from_epsg(4326), 1, 1)
    aoi = STGeometry(wgs84, shapely.geometry.box(*bbox), None).to_projection(projection)
    minx, miny, maxx, maxy = (int(v) for v in aoi.shp.bounds)

    labels: list[tuple[object, dict]] = []
    for feat in label_fc["features"]:
        geom = STGeometry(wgs84, shapely.geometry.shape(feat["geometry"]), None)
        labels.append((geom.to_projection(projection).shp, feat["properties"]))

    dataset = Dataset(UPath(dest))
    vector_format = GeojsonVectorFormat()

    n_built = 0
    n_empty = 0
    for wx in range(minx, maxx, window_px):
        for wy in range(miny, maxy, window_px):
            bounds = (wx, wy, wx + window_px, wy + window_px)
            cell = shapely.geometry.box(*bounds)

            hits = [(shp, props) for shp, props in labels if shp.intersects(cell)]
            positives = [p for shp, p in hits if p["class"] == 1]
            if len(positives) < MIN_POSITIVE_PX:
                n_empty += 1
                continue  # pure-negative window: a full S2 download that teaches nothing

            window = Window(
                storage=dataset.storage,
                group=group,
                name=f"{epsg}_{wx}_{wy}",
                projection=projection,
                bounds=bounds,
                time_range=TIME_RANGE,
            )
            window.save()

            features = [
                Feature(STGeometry(projection, shp.intersection(cell), None), props)
                for shp, props in hits
                if not shp.intersection(cell).is_empty
            ]
            vector_format.encode_vector(window.get_layer_dir("label"), features)
            window.mark_layer_completed("label")
            n_built += 1

    if n_built == 0:
        raise ValueError(
            "no window contains riparian label — a dataset of pure negatives trains happily and "
            "learns nothing. Check the bbox and the label layer before going further."
        )

    logger.info(
        "built %d windows (%d skipped: no riparian label — each would have been a full S2 "
        "download that teaches nothing)",
        n_built,
        n_empty,
    )
    return DatasetBuild(path=dest, n_windows=n_built, n_windows_skipped_empty=n_empty)


def verify_materialized(dest: Path, group: str = "train") -> int:
    """Assert the imagery is actually ON DISK. Never trust ``materialize``'s exit code.

    ``rslearn dataset materialize`` **exits 0 even when every window fails.** We hit exactly that:
    the scaffold said ``"ingest": false`` (the direct-materialize path), which requires the data
    source to implement ``get_item_by_name`` — and Planetary Computer's ``Sentinel2`` inherits the
    base implementation, which *raises ``NotImplementedError`` by design*. Every one of 238 windows
    threw, the exception was swallowed into a worker pool, and the command reported success while
    writing **zero** GeoTIFFs.

    A green exit code that means "did nothing" is the most expensive kind of green: on a GPU you
    would train on an empty cube, and the loss would fall anyway.

    Args:
        dest: Dataset root.
        group: Window group to check.

    Returns:
        The number of windows with materialized Sentinel-2 rasters.

    Raises:
        RuntimeError: If any window lacks imagery. Partial materialization is also a failure —
            silently training on the subset that happened to download is how you get a metric
            nobody can reproduce.
    """
    windows = sorted((dest / "windows" / group).iterdir())
    if not windows:
        raise RuntimeError(f"no windows under {dest}/windows/{group}")

    missing = [w.name for w in windows if not list(w.glob("layers/sentinel2*/**/*.tif"))]
    if missing:
        raise RuntimeError(
            f"{len(missing)} of {len(windows)} windows have NO Sentinel-2 raster on disk "
            f"(e.g. {missing[:3]}). `materialize` may have exited 0 anyway — it does that. "
            f"Check the log for NotImplementedError: with a Planetary Computer source, "
            f'`"ingest": false` is unsupported and fails silently.'
        )

    logger.info("✓ all %d windows have Sentinel-2 imagery on disk", len(windows))
    return len(windows)
