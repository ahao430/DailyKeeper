"""Scheduler daemon entrypoint: ``python -m app.scheduler``.

Loads plugins once at startup, then scans scheduled tasks on a fixed interval
and enqueues due executions for the worker pool.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.core.database import get_session_factory, init_engine
from app.services.plugin_runtime import load_plugins
from app.services.scheduler_service import scan_and_enqueue

logger = logging.getLogger(__name__)


async def tick(session_factory) -> int:
    """One scheduler pass: scan tasks and enqueue due executions."""
    async with session_factory() as session:
        created = await scan_and_enqueue(session)  # 内部已 commit
    return created


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    init_engine(settings)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await load_plugins(session)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        tick,
        "interval",
        args=[session_factory],
        seconds=settings.scheduler_interval_seconds,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    logger.info(
        "DailyKeeper Scheduler started (interval=%ss)", settings.scheduler_interval_seconds
    )
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
