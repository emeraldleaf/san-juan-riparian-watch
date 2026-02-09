"""ETL run tracking for the meta.etl_runs table.

Records the start, completion, and outcome of each ETL run,
including per-layer change flags and record counts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRecord:
    """Immutable snapshot of a completed ETL run."""

    id: int
    run_type: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    records_inserted: int
    records_updated: int
    records_skipped: int
    error_message: str | None
    streams_changed: bool
    parcels_changed: bool
    buffers_changed: bool


class RunTracker:
    """Manages ETL run lifecycle in meta.etl_runs.

    Args:
        engine: SQLAlchemy engine connected to PostGIS.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def start_run(self, run_type: str) -> int:
        """Insert a new run record and return its ID.

        Args:
            run_type: One of 'full', 'incremental', 'ndvi', 'all'.

        Returns:
            The auto-generated run ID.
        """
        sql = text("""
            INSERT INTO meta.etl_runs (run_type, status)
            VALUES (:run_type, 'running')
            RETURNING id
        """)
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"run_type": run_type}).fetchone()
            conn.commit()
        run_id: int = row[0]
        logger.info("Started ETL run %d (type=%s)", run_id, run_type)
        return run_id

    def complete_run(
        self,
        run_id: int,
        *,
        records_inserted: int = 0,
        records_updated: int = 0,
        records_skipped: int = 0,
        streams_changed: bool = False,
        parcels_changed: bool = False,
        buffers_changed: bool = False,
    ) -> None:
        """Mark a run as completed with aggregate counts.

        Args:
            run_id: The run to complete.
            records_inserted: Total rows inserted across all layers.
            records_updated: Total rows updated across all layers.
            records_skipped: Total rows unchanged across all layers.
            streams_changed: Whether bronze.streams had inserts or updates.
            parcels_changed: Whether bronze.parcels had inserts or updates.
            buffers_changed: Whether silver.riparian_buffers was regenerated.
        """
        sql = text("""
            UPDATE meta.etl_runs
            SET completed_at = now(),
                status = 'completed',
                records_inserted = :inserted,
                records_updated = :updated,
                records_skipped = :skipped,
                streams_changed = :streams,
                parcels_changed = :parcels,
                buffers_changed = :buffers
            WHERE id = :run_id
        """)
        with self._engine.connect() as conn:
            conn.execute(sql, {
                "run_id": run_id,
                "inserted": records_inserted,
                "updated": records_updated,
                "skipped": records_skipped,
                "streams": streams_changed,
                "parcels": parcels_changed,
                "buffers": buffers_changed,
            })
            conn.commit()
        logger.info(
            "Completed ETL run %d: %d inserted, %d updated, %d skipped",
            run_id, records_inserted, records_updated, records_skipped,
        )

    def fail_run(self, run_id: int, error: str) -> None:
        """Mark a run as failed with an error message.

        Args:
            run_id: The run to mark as failed.
            error: Human-readable error description.
        """
        sql = text("""
            UPDATE meta.etl_runs
            SET completed_at = now(),
                status = 'failed',
                error_message = :error
            WHERE id = :run_id
        """)
        with self._engine.connect() as conn:
            conn.execute(sql, {"run_id": run_id, "error": error})
            conn.commit()
        logger.error("Failed ETL run %d: %s", run_id, error)

    def get_last_successful_run(self, run_type: str) -> RunRecord | None:
        """Return the most recent successful run of the given type.

        Args:
            run_type: Filter by run type.

        Returns:
            RunRecord or None if no successful run exists.
        """
        sql = text("""
            SELECT id, run_type, started_at, completed_at, status,
                   records_inserted, records_updated, records_skipped,
                   error_message, streams_changed, parcels_changed,
                   buffers_changed
            FROM meta.etl_runs
            WHERE run_type = :run_type AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
        """)
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"run_type": run_type}).fetchone()
        if row is None:
            return None
        return RunRecord(
            id=row[0], run_type=row[1], started_at=row[2],
            completed_at=row[3], status=row[4], records_inserted=row[5],
            records_updated=row[6], records_skipped=row[7],
            error_message=row[8], streams_changed=row[9],
            parcels_changed=row[10], buffers_changed=row[11],
        )
