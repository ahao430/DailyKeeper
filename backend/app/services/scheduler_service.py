"""Scheduler service: scan scheduled tasks and enqueue due executions.

Also writes a heartbeat so a second (accidental) scheduler instance can be
detected from the ``system_settings`` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import next_occurrence, now_utc
from app.models import (
    Account,
    PlatformInstance,
    ScheduledTask,
    SystemSetting,
)
from app.models.tables import ACCOUNT_STATUS_DISABLED
from app.services.task_engine import create_execution

logger = logging.getLogger(__name__)

SCHEDULER_HEARTBEAT_KEY = "scheduler_heartbeat"

# 模块级调度器实例 ID：每个进程启动时生成一次，用于心跳互斥检测
scheduler_id = uuid4().hex


async def scan_and_enqueue(session: AsyncSession) -> int:
    """Scan all enabled scheduled tasks and create executions for due ones.

    Commits the session and returns the number of executions created.
    """
    settings = get_settings()
    now = now_utc()

    heartbeat = await session.get(SystemSetting, SCHEDULER_HEARTBEAT_KEY)
    if heartbeat is not None:
        value = heartbeat.value or {}
        other_id = str(value.get("id") or "")
        if other_id and other_id != scheduler_id:
            at = _parse_heartbeat_time(value.get("at"))
            if at is not None and (now - at).total_seconds() <= 3 * settings.scheduler_interval_seconds:
                logger.warning("检测到其他调度器心跳（可能多实例运行），仍将继续")

    heartbeat_value = {"id": scheduler_id, "at": now.isoformat()}
    if heartbeat is None:
        session.add(SystemSetting(key=SCHEDULER_HEARTBEAT_KEY, value=heartbeat_value))
    else:
        heartbeat.value = heartbeat_value

    rows = (
        await session.execute(
            select(ScheduledTask, Account, PlatformInstance)
            .join(Account, ScheduledTask.account_id == Account.id)
            .join(PlatformInstance, Account.instance_id == PlatformInstance.id)
            .where(
                ScheduledTask.enabled.is_(True),
                # Account 的启停由 status 表达（DISABLED 即停用）
                Account.status != ACCOUNT_STATUS_DISABLED,
                PlatformInstance.enabled.is_(True),
            )
        )
    ).all()

    created = 0
    for scheduled_task, account, instance in rows:
        if scheduled_task.next_run_at is None:
            # 首次见到该计划任务：只初始化下次运行时间，不入队
            scheduled_task.next_run_at = next_occurrence(
                scheduled_task.time_of_day, scheduled_task.interval_days, instance.timezone, after=now
            )
            continue

        if scheduled_task.next_run_at <= now:
            execution = await create_execution(
                session,
                account,
                scheduled_task.task_name,
                scheduled_task_id=scheduled_task.id,
                params=scheduled_task.params,
                due_at=now,
            )
            scheduled_task.last_run_at = now
            scheduled_task.next_run_at = next_occurrence(
                scheduled_task.time_of_day, scheduled_task.interval_days, instance.timezone, after=now
            )
            if execution is not None:
                created += 1

    await session.commit()
    if created:
        logger.info("本轮调度入队 %s 个任务", created)
    return created


def _parse_heartbeat_time(raw) -> datetime | None:
    """Parse a heartbeat timestamp; tolerate missing or malformed values."""
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc).replace(tzinfo=None)
    return at
