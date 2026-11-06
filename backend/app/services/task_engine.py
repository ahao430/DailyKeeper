"""Task engine: creation with idempotency, claiming, recovery and finalization.

Finalization writes the result row, updates account status, persists resource
snapshots, dispatches notifications and schedules retries.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dailykeeper_sdk import TaskResult, TaskStatus

from app.core.config import get_settings
from app.core.timeutil import date_in_tz, now_utc
from app.models import (
    Account,
    PlatformInstance,
    ResourceSnapshot,
    TaskExecution,
    TaskResultRecord,
)
from app.models.tables import ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_AUTH_EXPIRED
from app.services import notification_service
from dailykeeper_sdk.registry import plugin_registry

logger = logging.getLogger(__name__)

# Agent 心跳离线判定窗口（秒）：超过该时长未心跳的 ONLINE Agent 被扫为离线。
# 定义在 task_engine 以避免调度器与 API 层之间的循环导入。
AGENT_OFFLINE_SECONDS = 90

# 业务日期内视为“已存在执行”的状态（成功/进行中的结果不重复排队）
DEDUPE_STATUSES = ("PENDING", "RUNNING", "SUCCESS", "AUTH_EXPIRED", "NEEDS_ACTION")

_EVENT_BY_STATUS: dict[TaskStatus, str | None] = {
    TaskStatus.FAILED: "task_failed",
    TaskStatus.AUTH_EXPIRED: "auth_expired",
    TaskStatus.NEEDS_ACTION: "needs_action",
    TaskStatus.RATE_LIMITED: "rate_limited",
    TaskStatus.SUCCESS: "task_success",
    TaskStatus.SKIPPED: None,
    TaskStatus.INTERRUPTED: None,
}

_EVENT_TITLES = {
    "task_failed": "任务执行失败",
    "auth_expired": "登录状态失效",
    "needs_action": "任务需要人工处理",
    "rate_limited": "任务触发限流",
    "task_success": "任务执行成功",
}


def business_date_for(instance: PlatformInstance) -> date:
    """Current business date for a platform instance (its site-local calendar date)."""
    return date_in_tz(instance.timezone)


async def today_dedupe_status(
    session: AsyncSession, account: Account, task_name: str
) -> str | None:
    """Status of today's dedupe-state execution for (account, task); None when free to run."""
    bd = business_date_for(account.instance)
    row = await session.execute(
        select(TaskExecution.status)
        .where(
            TaskExecution.account_id == account.id,
            TaskExecution.task_name == task_name,
            TaskExecution.business_date == bd,
            TaskExecution.status.in_(DEDUPE_STATUSES),
        )
        .order_by(TaskExecution.id.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def create_execution(
    session: AsyncSession,
    account: Account,
    task_name: str,
    *,
    scheduled_task_id: int | None = None,
    params: dict | None = None,
    due_at=None,
    retries: int = 0,
    force: bool = False,
) -> TaskExecution | None:
    """Create a PENDING execution unless the business date already has one.

    Returns ``None`` when deduplicated (an execution with a DEDUPE_STATUSES
    status already exists for this account/task/business_date). Flushes but
    does not commit; the caller owns the transaction.
    """
    instance = account.instance
    bd = business_date_for(instance)

    # 任务声明为需要浏览器/Agent 时，执行记录打标，分流到对应执行线
    plugin = plugin_registry.get(instance.platform_id)
    task_def = next(
        (t for t in plugin.task_definitions if t.name == task_name), None
    ) if plugin is not None else None
    needs_browser = bool(task_def and task_def.requires_browser)
    needs_agent = bool(task_def and task_def.requires_agent)

    if not force:
        existing_id = await session.scalar(
            select(TaskExecution.id)
            .where(
                TaskExecution.account_id == account.id,
                TaskExecution.task_name == task_name,
                TaskExecution.business_date == bd,
                TaskExecution.status.in_(DEDUPE_STATUSES),
            )
            .limit(1)
        )
        if existing_id is not None:
            return None

    execution = TaskExecution(
        account_id=account.id,
        scheduled_task_id=scheduled_task_id,
        task_name=task_name,
        business_date=bd,
        status="PENDING",
        params=params or {},
        retries=retries,
        needs_browser=needs_browser,
        needs_agent=needs_agent,
        due_at=due_at or now_utc(),
    )
    session.add(execution)
    await session.flush()
    return execution


async def claim_pending(
    session: AsyncSession, worker_id: str, limit: int, *, browser: bool = False
) -> list[TaskExecution]:
    """Atomically claim up to ``limit`` due PENDING executions for one worker.

    ``browser=True`` claims only executions that need browser automation; the
    regular worker claims the rest — agent-lane executions are claimed by
    neither (local agents pull them via ``claim_agent_tasks``). The claim is a
    conditional UPDATE (status PENDING -> RUNNING), so two workers never take
    the same execution. Rows actually owned by this worker are returned
    ordered by id. Does not commit; the caller commits.
    """
    now = now_utc()
    if browser:
        lane_filter = TaskExecution.needs_browser.is_(True)
    else:  # HTTP 执行线：既不要浏览器任务，也不要 Agent 任务
        lane_filter = (TaskExecution.needs_browser.is_(False)) & (
            TaskExecution.needs_agent.is_(False)
        )
    ids = (
        await session.scalars(
            select(TaskExecution.id)
            .where(
                TaskExecution.status == "PENDING",
                TaskExecution.due_at.is_(None) | (TaskExecution.due_at <= now),
                lane_filter,
            )
            .order_by(TaskExecution.id)
            .limit(limit)
        )
    ).all()
    if not ids:
        return []

    await session.execute(
        update(TaskExecution)
        .where(TaskExecution.id.in_(ids), TaskExecution.status == "PENDING")
        .values(status="RUNNING", worker_id=worker_id, started_at=now)
        .execution_options(synchronize_session=False)
    )
    claimed = (
        await session.scalars(
            select(TaskExecution)
            .where(
                TaskExecution.id.in_(ids),
                TaskExecution.worker_id == worker_id,
                TaskExecution.status == "RUNNING",
            )
            .order_by(TaskExecution.id)
        )
    ).all()
    return list(claimed)


async def claim_agent_tasks(session: AsyncSession, agent, limit: int) -> list[TaskExecution]:
    """Claim due PENDING agent-lane executions for one local agent.

    Same conditional-UPDATE pattern as ``claim_pending``: sets RUNNING,
    ``worker_id = agent-<id>`` and ``assigned_agent_id``. Does not commit.
    """
    now = now_utc()
    ids = (
        await session.scalars(
            select(TaskExecution.id)
            .where(
                TaskExecution.status == "PENDING",
                TaskExecution.due_at.is_(None) | (TaskExecution.due_at <= now),
                TaskExecution.needs_agent.is_(True),
            )
            .order_by(TaskExecution.id)
            .limit(limit)
        )
    ).all()
    if not ids:
        return []

    worker_id = f"agent-{agent.id}"
    await session.execute(
        update(TaskExecution)
        .where(TaskExecution.id.in_(ids), TaskExecution.status == "PENDING")
        .values(
            status="RUNNING", worker_id=worker_id, assigned_agent_id=agent.id, started_at=now
        )
        .execution_options(synchronize_session=False)
    )
    claimed = (
        await session.scalars(
            select(TaskExecution)
            .where(
                TaskExecution.id.in_(ids),
                TaskExecution.worker_id == worker_id,
                TaskExecution.status == "RUNNING",
            )
            .order_by(TaskExecution.id)
        )
    ).all()
    return list(claimed)


async def recover_interrupted(session: AsyncSession, *, browser: bool | None = None) -> int:
    """Mark RUNNING executions as INTERRUPTED after a service restart.

    ``browser`` filters by execution lane so one worker daemon restarting
    never interrupts the other kind's in-flight executions; agent-lane
    executions are recovered by the offline sweep (or agent deletion),
    not by server daemons, because the agent may still be running them.
    Each one gets a failure result record so the dashboard can show why it
    stopped. Commits the session and returns the number of recovered rows.
    """
    now = now_utc()
    query = select(TaskExecution).where(TaskExecution.status == "RUNNING")
    if browser is not None:
        query = query.where(
            TaskExecution.needs_browser.is_(browser), TaskExecution.needs_agent.is_(False)
        )
    running = (await session.scalars(query)).all()
    for execution in running:
        execution.status = "INTERRUPTED"
        execution.finished_at = now
        session.add(
            TaskResultRecord(
                execution_id=execution.id,
                success=False,
                status="INTERRUPTED",
                message="任务因服务重启中断，可手动重试",
            )
        )
    await session.commit()
    if running:
        logger.warning("已将 %s 个运行中任务标记为中断", len(running))
    return len(running)


def _persist_resources(
    session: AsyncSession,
    execution: TaskExecution,
    account: Account,
    instance: PlatformInstance,
    resources: list,
    now,
) -> None:
    """Persist resource snapshots from a successful result payload."""
    for entry in resources:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        text_value = entry.get("text_value")
        if value is None and (text_value is None or str(text_value) == ""):
            continue
        session.add(
            ResourceSnapshot(
                account_id=account.id,
                execution_id=execution.id,
                resource_type=str(entry.get("resource_type") or ""),
                value=Decimal(str(value)) if value is not None else None,
                text_value=None if text_value is None else str(text_value),
                unit=str(entry.get("unit") or ""),
                observed_at=entry.get("observed_at") or now,
                source=instance.platform_id,
            )
        )


async def finalize_execution(
    session: AsyncSession, execution: TaskExecution, result: TaskResult
) -> None:
    """Apply a task result: status, result row, account state, snapshots,
    notifications and retry scheduling. Commits the session.
    """
    settings = get_settings()
    now = now_utc()

    status = result.status
    if status == TaskStatus.RUNNING:  # 防御：RUNNING 不能作为最终状态
        status = TaskStatus.FAILED

    execution.status = status.value
    execution.finished_at = now

    record = await session.scalar(
        select(TaskResultRecord).where(TaskResultRecord.execution_id == execution.id)
    )
    if record is None:
        record = TaskResultRecord(execution_id=execution.id)
        session.add(record)
    record.success = result.success
    record.status = status.value
    record.message = result.message
    record.data = result.data
    record.metrics = result.metrics

    account = await session.get(Account, execution.account_id)
    instance = account.instance if account is not None else None

    if account is not None:
        if status == TaskStatus.AUTH_EXPIRED:
            account.status = ACCOUNT_STATUS_AUTH_EXPIRED
        elif status == TaskStatus.SUCCESS:
            # 以下字段为可选扩展列；当前 Account 模型未包含时跳过
            if hasattr(account, "last_task_at"):
                account.last_task_at = now
            if account.status == ACCOUNT_STATUS_AUTH_EXPIRED:
                account.status = ACCOUNT_STATUS_ACTIVE
            if execution.task_name == "daily_checkin" and hasattr(account, "last_checkin_date"):
                account.last_checkin_date = execution.business_date

        if (
            status == TaskStatus.SUCCESS
            and isinstance(result.data.get("resources"), list)
            and instance is not None
        ):
            _persist_resources(session, execution, account, instance, result.data["resources"], now)

    will_retry = (
        status == TaskStatus.FAILED
        and bool((result.data or {}).get("retryable"))
        and execution.retries < settings.max_retries
    )

    if not will_retry:
        event = _EVENT_BY_STATUS.get(status)
        if event is not None:
            await notification_service.notify(
                session,
                event,
                title=f"[DailyKeeper] {_EVENT_TITLES[event]}",
                body=result.message or _EVENT_TITLES[event],
                context={
                    "execution_id": execution.id,
                    "account_id": execution.account_id,
                    "account_name": account.name if account is not None else "",
                    "platform_id": instance.platform_id if instance is not None else "",
                    "task_name": execution.task_name,
                    "business_date": str(execution.business_date),
                    "message": result.message,
                    "status": status.value,
                },
            )

    if will_retry and account is not None:
        await create_execution(
            session,
            account,
            execution.task_name,
            scheduled_task_id=execution.scheduled_task_id,
            params=execution.params,
            due_at=now_utc()
            + timedelta(seconds=settings.retry_backoff_seconds * (execution.retries + 1)),
            retries=execution.retries + 1,
            force=True,
        )
        logger.info(
            "任务失败将重试 execution_id=%s retry=%s/%s",
            execution.id,
            execution.retries + 1,
            settings.max_retries,
        )

    await session.commit()
