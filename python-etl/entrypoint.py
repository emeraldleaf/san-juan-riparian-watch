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
from ndvi_processor import (
    NdviProcessor,
    PlanetaryComputerSearcher,
    PostGISNdviWriter,
)
from run_tracker import RunTracker

logger = logging.getLogger(__name__)


def execute_run(update_type: str) -> None:
    """Execute a single ETL run of the given type.

    Args:
        update_type: One of 'full', 'incremental', 'ndvi', 'all'.
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
    )

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
    args = parser.parse_args()

    import os
    mode = args.mode or os.environ.get("ETL_MODE", "full")

    if mode == "scheduled":
        from scheduler import get_schedule_config, run_scheduled
        run_scheduled(execute_run, get_schedule_config())
    else:
        execute_run(mode)


if __name__ == "__main__":
    main()
