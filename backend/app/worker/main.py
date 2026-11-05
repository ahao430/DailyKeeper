"""Worker daemon entrypoint: ``python -m app.worker``.

Polls for due PENDING executions, claims them atomically, and runs each one
with a per-account lock so tasks of the same account never run concurrently.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.core.database import ensure_schema, get_session_factory, init_engine
from app.core.security import get_cipher
from app.services.plugin_runtime import load_plugins, run_execution
from app.services.task_engine import claim_pending, recover_interrupted

logger = logging.getLogger(__name__)


async def _run_with_lock(
    execution_id: int,
    account_id: int,
    locks: dict[int, asyncio.Lock],
    session_factory,
    cipher,
    settings: Settings,
) -> None:
    """Run one execution while holding the account's lock."""
    async with locks[account_id]:
        await run_execution(
            execution_id, session_factory=session_factory, cipher=cipher, settings=settings
        )


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    init_engine(settings)
    session_factory = get_session_factory()

    await ensure_schema()  # 与 API 进程并行启动时避免建表竞态
    async with session_factory() as session:
        await load_plugins(session)
        recovered = await recover_interrupted(session, browser=False)  # 仅恢复 HTTP 任务
    if recovered:
        logger.info("已恢复 %s 个因重启中断的任务", recovered)

    cipher = get_cipher(settings)
    worker_id = f"worker-{uuid4().hex[:8]}"
    locks: dict[int, asyncio.Lock] = {}
    logger.info(
        "DailyKeeper Worker started (%s, concurrency=%s)", worker_id, settings.worker_concurrency
    )

    while True:
        async with session_factory() as session:
            executions = await claim_pending(session, worker_id, limit=settings.worker_concurrency)
            await session.commit()

        if not executions:
            await asyncio.sleep(settings.worker_poll_seconds)
            continue

        for execution in executions:
            locks.setdefault(execution.account_id, asyncio.Lock())
        tasks = [
            asyncio.create_task(
                _run_with_lock(
                    execution.id,
                    execution.account_id,
                    locks,
                    session_factory,
                    cipher,
                    settings,
                )
            )
            for execution in executions
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
