"""ETL entrypoint supporting one-shot, incremental, NDVI, and scheduled modes.

Usage:
    python entrypoint.py                    # One-shot full run (default)
    python entrypoint.py --mode full        # Explicit full run
    python entrypoint.py --mode incremental # Incremental upsert
    python entrypoint.py --mode ndvi        # NDVI refresh only
    python entrypoint.py --mode all         # Incremental + NDVI
    python entrypoint.py --mode scheduled   # Long-lived scheduler
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine

from etl_pipeline import (
    ArcGISFeatureClient,
    EtlPipeline,
    PostGISWriter,
    _resolve_database_url,
)
from health_scorer import HealthScorer
from landfire_processor import (
    LANDFIRE_EVH_URL,
    LANDFIRE_EVT_URL,
    LandfireProcessor,
    PostGISLandfireWriter,
)
from lidar_processor import LidarProcessor
from ndvi_processor import (
    NdviProcessor,
    PlanetaryComputerSearcher,
    PostGISNdviWriter,
)
from nlcd_processor import NLCD_EROS_URL, NLCD_IMAGE_SERVER_URL, NlcdProcessor, PostGISNlcdWriter
from raster_processor import FallbackRasterSource, GeoServerWmsSource, ImageServerSource
from run_tracker import RunTracker
from ssurgo_processor import SsurgoProcessor

logger = logging.getLogger(__name__)


def execute_run(update_type: str, *, force_reload: bool = False) -> None:
    """Execute a single ETL run of the given type.

    Args:
        update_type: One of 'full', 'incremental', 'ndvi', 'all'.
        force_reload: If True, re-fetch all data even if tables are
            already populated (e.g. NWI wetlands).
    """
    url = _resolve_database_url()
    if not url:
        logger.error("No database URL found")
        sys.exit(1)

    engine = create_engine(url)
    tracker = RunTracker(engine)
    pipeline = EtlPipeline(
        client=ArcGISFeatureClient(),
        writer=PostGISWriter(engine),
        force_reload=force_reload,
    )

    # Wire up enrichment processors (NLCD, LANDFIRE, SSURGO, LiDAR, scorer)
    # NLCD: Try EROS ImageServer first; fall back to MRLC GeoServer WMS
    nlcd_primary = ImageServerSource(base_url=NLCD_EROS_URL)
    nlcd_fallback = GeoServerWmsSource(
        base_url=NLCD_IMAGE_SERVER_URL,
        layers="NLCD_2021_Land_Cover_L48",
        palette_to_value=GeoServerWmsSource.NLCD_PALETTE_MAP,
    )
    nlcd_source = FallbackRasterSource(primary=nlcd_primary, fallback=nlcd_fallback)
    nlcd_writer = PostGISNlcdWriter(engine=engine)
    nlcd_proc = NlcdProcessor(source=nlcd_source, writer=nlcd_writer, engine=engine)

    evt_source = ImageServerSource(base_url=LANDFIRE_EVT_URL)
    evh_source = ImageServerSource(base_url=LANDFIRE_EVH_URL)
    lf_writer = PostGISLandfireWriter(engine=engine)
    landfire_proc = LandfireProcessor(
        evt_source=evt_source, evh_source=evh_source,
        writer=lf_writer, engine=engine,
    )

    pipeline.set_raster_processors(nlcd_proc, landfire_proc)
    pipeline.set_ssurgo_processor(SsurgoProcessor(engine))
    # LiDAR disabled: 3DEP per-buffer tile lookups too slow for 6747 buffers.
    # TODO: Re-enable after optimizing spatial tile index.
    # pipeline.set_lidar_processor(LidarProcessor(engine))
    pipeline.set_health_scorer(HealthScorer(engine))

    run_id = tracker.start_run(update_type)
    try:
        if update_type == "full":
            pipeline.run()
            tracker.complete_run(run_id)

        elif update_type == "incremental":
            streams_changed, parcels_changed, buffers_changed = (
                pipeline.run_incremental()
            )
            tracker.complete_run(
                run_id,
                streams_changed=streams_changed,
                parcels_changed=parcels_changed,
                buffers_changed=buffers_changed,
            )

        elif update_type == "ndvi":
            count = _run_ndvi(engine)
            pipeline.update_summary_ndvi()
            tracker.complete_run(run_id, records_inserted=count)

        elif update_type == "all":
            streams_changed, parcels_changed, buffers_changed = (
                pipeline.run_incremental()
            )
            ndvi_count = _run_ndvi(engine)
            pipeline.update_summary_ndvi()
            tracker.complete_run(
                run_id,
                records_inserted=ndvi_count,
                streams_changed=streams_changed,
                parcels_changed=parcels_changed,
                buffers_changed=buffers_changed,
            )

        else:
            raise ValueError(f"Unknown update type: {update_type}")

    except Exception as exc:
        tracker.fail_run(run_id, str(exc))
        raise


def _run_ndvi(engine: object) -> int:
    """Run incremental NDVI processing.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Number of new readings written.
    """
    processor = NdviProcessor(
        searcher=PlanetaryComputerSearcher(),
        writer=PostGISNdviWriter(engine),
        engine=engine,
    )
    return processor.process_buffers_incremental()


def main() -> None:
    """Parse arguments and dispatch to the appropriate run mode."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Riparian ETL entrypoint")
    parser.add_argument(
        "--mode", default=None,
        choices=["full", "incremental", "ndvi", "all", "scheduled"],
        help="Run mode (default: full for backwards compatibility)",
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help="Force re-fetch of all data, even if tables are populated",
    )
    args = parser.parse_args()

    import os
    mode = args.mode or os.environ.get("ETL_MODE", "full")

    if mode == "scheduled":
        from scheduler import get_schedule_config, run_scheduled
        run_scheduled(execute_run, get_schedule_config())
    else:
        execute_run(mode, force_reload=args.force)


if __name__ == "__main__":
    main()
