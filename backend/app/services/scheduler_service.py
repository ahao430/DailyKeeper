"""Scheduler service: scan scheduled tasks and enqueue due executions.

Also writes a heartbeat so a second (accidental) scheduler instance can be
detected from the ``system_settings`` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutil import next_occurrence, now_utc
from app.models import (
    Account,
    Agent,
    PlatformInstance,
    ScheduledTask,
    SystemSetting,
    TaskExecution,
    TaskResultRecord,
)
from app.models.tables import ACCOUNT_STATUS_DISABLED
from app.services import notification_service
from app.services.task_engine import AGENT_OFFLINE_SECONDS, create_execution

logger = logging.getLogger(__name__)

SCHEDULER_HEARTBEAT_KEY = "scheduler_heartbeat"

# 模块级调度器实例 ID：每个进程启动时生成一次，用于心跳互斥检测
scheduler_id = uuid4().hex


async def sweep_offline_agents(session: AsyncSession, *, now=None) -> int:
    """把心跳超时的 ONLINE Agent 标记为 OFFLINE，并中断其运行中执行。

    每个被扫掉的 Agent 记录一条 ``agent_offline`` 通知（事件默认启用，无
    渠道时仍会落一条 SKIPPED 记录）。不提交事务；由调用方
    （``scan_and_enqueue``）统一提交。返回被标记离线的 Agent 数。
    """
    now = now or now_utc()
    deadline = now - timedelta(seconds=AGENT_OFFLINE_SECONDS)
    agents = (
        await session.scalars(
            select(Agent).where(
                Agent.status == "ONLINE",
                Agent.last_heartbeat.isnot(None),
                Agent.last_heartbeat < deadline,
            )
        )
    ).all()
    if not agents:
        return 0

    for agent in agents:
        agent.status = "OFFLINE"
        running = (
            await session.scalars(
                select(TaskExecution).where(
                    TaskExecution.assigned_agent_id == agent.id,
                    TaskExecution.status == "RUNNING",
                )
            )
        ).all()
        for execution in running:
            execution.status = "INTERRUPTED"
            execution.finished_at = now
            session.add(
                TaskResultRecord(
                    execution_id=execution.id,
                    success=False,
                    status="INTERRUPTED",
                    message="Agent 离线超时，任务中断",
                )
            )
        await notification_service.notify(
            session,
            "agent_offline",
            title="[DailyKeeper] Agent 离线",
            body=(
                f"Agent {agent.name} 超过 {AGENT_OFFLINE_SECONDS} 秒未心跳，"
                f"已标记离线，其 {len(running)} 个运行中任务已中断"
            ),
            context={"agent_id": agent.id, "agent_name": agent.name},
        )
        logger.warning(
            "Agent 心跳超时标记离线 agent=%s id=%s 中断执行数=%s",
            agent.name,
            agent.id,
            len(running),
        )
    return len(agents)


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

    # Agent 离线清扫：放在任务扫描之前，保证入队/中断决策基于最新健康状态
    await sweep_offline_agents(session, now=now)

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
