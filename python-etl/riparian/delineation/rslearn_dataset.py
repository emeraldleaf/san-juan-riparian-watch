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


class EmptyDatasetError(RuntimeError):
    """No window contained riparian label, or materialisation wrote nothing to disk.

    A distinct type (not a bare ``ValueError``) so callers and the CLI can tell "the build produced
    an unusable dataset" apart from an ordinary bad-argument error — the whole point of Phase 0 is
    to fail loudly *here*, on a laptop, rather than discover an empty cube on a rented GPU.
    """


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
        EmptyDatasetError: If no window contains any riparian label — a dataset of pure negatives
            would train happily and learn nothing.
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
            # Count positive PIXELS, not positive polygons. Geometries are in the projection's pixel
            # grid, so a clipped polygon's area IS its pixel count — which is what MIN_POSITIVE_PX
            # means. Comparing len(positives) would count polygons, so raising the threshold would
            # silently start demanding N distinct polygons instead of N pixels.
            positive_px = sum(
                shp.intersection(cell).area for shp, p in hits if p["class"] == 1
            )
            if positive_px < MIN_POSITIVE_PX:
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
        raise EmptyDatasetError(
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


def rasterize_labels_and_split(dest: Path, group: str = "train", val_fraction: int = 3) -> tuple[int, int]:
    """Rasterize each window's vector ``label`` into a ``label_raster`` layer, and tag a split.

    The model reads a **raster** segmentation target (``label_raster``, band ``label``, INT32), but
    the label layer is authored as **vector** GeoJSON — that is the natural form for NMRipMap
    polygons, and it is what lets the imagery validator overlay and shift them. rslearn does not
    rasterize a vector layer into a training target on its own when you drive ``model fit``
    directly, so we do it here, once, into the exact on-disk shape the sentinel2 layers use.

    Class id 0 is left as background/no-label — with ``zero_is_invalid: true`` the loss ignores it,
    so unlabeled pixels inside a window neither reward nor punish the model.

    **The split is spatial, not random.** Windows are assigned to val by hashing their grid cell,
    so spatially autocorrelated neighbours cannot straddle the train/val boundary — the same
    discipline as ``riparian/delineation/validate.py``. A random split here would leak the answer
    across the boundary and inflate every val metric; the AUC-0.23 incident was the *inverse* of
    this (an unshuffled split that looked like a model failure), and both come from the same root:
    a split that does not respect space.

    Args:
        dest: Dataset root.
        group: Window group.
        val_fraction: 1-in-N windows go to val (hash-based, deterministic).

    Returns:
        ``(n_rasterized, n_val)``.
    """
    import json

    import numpy as np
    import shapely
    from rasterio.features import rasterize
    from rslearn.utils.raster_format import GeotiffRasterFormat

    from rslearn.dataset import Dataset
    from upath import UPath

    dataset = Dataset(UPath(dest))
    fmt = GeotiffRasterFormat()
    windows = dataset.load_windows(groups=[group])

    n_rasterized = 0
    n_val = 0
    for window in windows:
        label_dir = window.get_layer_dir("label")
        geojson_path = label_dir / "data.geojson"
        with geojson_path.open() as f:
            fc = json.load(f)

        wx0, wy0, wx1, wy1 = window.bounds
        h, w = wy1 - wy0, wx1 - wx0
        # Window pixel bounds are in projection units; shift geometries into the window's pixel grid.
        shapes = []
        for feat in fc["features"]:
            geom = shapely.affinity.translate(
                shapely.geometry.shape(feat["geometry"]), xoff=-wx0, yoff=-wy0
            )
            shapes.append((geom, int(feat["properties"]["class"])))

        raster = rasterize(
            shapes, out_shape=(h, w), fill=0, dtype="int32", all_touched=False
        ) if shapes else np.zeros((h, w), dtype="int32")

        raster_dir = window.get_raster_dir("label_raster", ["label"])
        fmt.encode_raster(raster_dir, window.projection, window.bounds, raster[None, :, :])
        window.mark_layer_completed("label_raster")
        n_rasterized += 1

        # Deterministic spatial split: hash the grid cell, not a random draw.
        cell_hash = hash((wx0 // 32, wy0 // 32)) % val_fraction
        split = "val" if cell_hash == 0 else "train"
        window.options = {**window.options, "split": split}
        window.save()
        if split == "val":
            n_val += 1

    logger.info(
        "rasterized %d label rasters; spatial split -> %d train / %d val",
        n_rasterized,
        n_rasterized - n_val,
        n_val,
    )
    return n_rasterized, n_val


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
        EmptyDatasetError: If any window lacks imagery. Partial materialization is also a failure —
            silently training on the subset that happened to download is how you get a metric
            nobody can reproduce.
    """
    group_dir = dest / "windows" / group
    if not group_dir.is_dir():
        # iterdir() would raise a bare FileNotFoundError; callers expect the domain exception.
        raise EmptyDatasetError(f"no windows under {group_dir} — it does not exist")
    windows = sorted(group_dir.iterdir())
    if not windows:
        raise EmptyDatasetError(f"no windows under {group_dir}")

    missing = [w.name for w in windows if not list(w.glob("layers/sentinel2*/**/*.tif"))]
    if missing:
        raise EmptyDatasetError(
            f"{len(missing)} of {len(windows)} windows have NO Sentinel-2 raster on disk "
            f"(e.g. {missing[:3]}). `materialize` may have exited 0 anyway — it does that. "
            f"Check the log for NotImplementedError: with a Planetary Computer source, "
            f'`"ingest": false` is unsupported and fails silently.'
        )

    logger.info("✓ all %d windows have Sentinel-2 imagery on disk", len(windows))
    return len(windows)
