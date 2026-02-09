"""Configurable ETL scheduler.

Reads schedule configuration from environment variables and
runs the ETL pipeline on a recurring basis. Falls back to
one-shot execution if no schedule is configured.

Environment variables:
    ETL_SCHEDULE_CRON: Cron expression (e.g., ``'0 2 * * *'`` for 2 AM daily).
    ETL_SCHEDULE_INTERVAL_HOURS: Alternative — run every N hours.
    ETL_UPDATE_TYPE: ``'full'``, ``'incremental'``, ``'ndvi'``, or ``'all'``
                     (default: ``'incremental'``).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from typing import Callable

logger = logging.getLogger(__name__)


def get_schedule_config() -> dict[str, str]:
    """Read scheduler configuration from environment variables.

    Returns:
        Dict with keys: mode, cron, interval_hours, update_type.
    """
    return {
        "mode": os.environ.get("ETL_MODE", "full"),
        "cron": os.environ.get("ETL_SCHEDULE_CRON", ""),
        "interval_hours": os.environ.get("ETL_SCHEDULE_INTERVAL_HOURS", ""),
        "update_type": os.environ.get("ETL_UPDATE_TYPE", "incremental"),
    }


def run_scheduled(
    run_fn: Callable[[str], None],
    config: dict[str, str],
) -> None:
    """Start the APScheduler event loop with the given run function.

    Args:
        run_fn: Callable that accepts an update_type string and executes it.
        config: Schedule configuration from ``get_schedule_config()``.

    Raises:
        SystemExit: If no schedule is configured.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BlockingScheduler()
    update_type = config["update_type"]

    if config["cron"]:
        trigger = CronTrigger.from_crontab(config["cron"])
        scheduler.add_job(
            run_fn, trigger, args=[update_type],
            id="etl_update", max_instances=1,
        )
        logger.info(
            "Scheduled ETL (%s) with cron: %s", update_type, config["cron"],
        )
    elif config["interval_hours"]:
        hours = int(config["interval_hours"])
        trigger = IntervalTrigger(hours=hours)
        scheduler.add_job(
            run_fn, trigger, args=[update_type],
            id="etl_update", max_instances=1,
        )
        logger.info(
            "Scheduled ETL (%s) every %d hours", update_type, hours,
        )
    else:
        logger.error(
            "ETL_MODE=scheduled but no schedule configured. "
            "Set ETL_SCHEDULE_CRON or ETL_SCHEDULE_INTERVAL_HOURS."
        )
        sys.exit(1)

    def shutdown(signum: int, _frame: object) -> None:
        logger.info("Received signal %d, shutting down scheduler", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("Scheduler started. Waiting for next run...")
    scheduler.start()
