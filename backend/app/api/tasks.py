"""Scheduled task management: list, create and run-now enqueue."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dailykeeper_sdk.registry import plugin_registry

from app.api.deps import get_current_admin, get_db
from app.core.timeutil import next_occurrence, now_utc, parse_hhmm
from app.models import Account, ScheduledTask, TaskExecution
from app.services.task_engine import create_execution

router = APIRouter(
    prefix="/api/scheduled-tasks", tags=["tasks"], dependencies=[Depends(get_current_admin)]
)


class CreateScheduledTaskRequest(BaseModel):
    account_id: int
    task_name: str
    time_of_day: str = "08:30"
    interval_days: int = 1
    params: dict = {}
    enabled: bool = True


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _task_detail(task: ScheduledTask, account: Account) -> dict:
    """Serialize one scheduled task; computes a next-run preview when not yet scheduled."""
    instance = account.instance
    next_run_at = task.next_run_at
    if next_run_at is None:
        next_run_at = next_occurrence(
            task.time_of_day, task.interval_days, instance.timezone, after=now_utc()
        )
    return {
        "id": task.id,
        "account_id": task.account_id,
        "account_name": account.name,
        "platform_id": instance.platform_id,
        "instance_name": instance.name,
        "timezone": instance.timezone,
        "task_name": task.task_name,
        "time_of_day": task.time_of_day,
        "interval_days": task.interval_days,
        "params": task.params,
        "enabled": task.enabled,
        "next_run_at": _dt(next_run_at),  # 未持久化的仅为预览值
        "last_run_at": _dt(task.last_run_at),
    }


@router.get("")
async def list_scheduled_tasks(
    account_id: int | None = Query(None), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """All scheduled tasks, optionally filtered by account."""
    query = (
        select(ScheduledTask, Account)
        .join(Account, ScheduledTask.account_id == Account.id)
        .order_by(ScheduledTask.id)
    )
    if account_id is not None:
        query = query.where(ScheduledTask.account_id == account_id)
    rows = (await session.execute(query)).all()
    return [_task_detail(task, account) for task, account in rows]


@router.post("")
async def create_scheduled_task(payload: CreateScheduledTaskRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Create a recurring task after validating it against the platform plugin."""
    account = await session.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    plugin = plugin_registry.get(account.instance.platform_id)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail=f"平台插件未加载: {account.instance.platform_id}"
        )
    declared = {task_def.name for task_def in plugin.task_definitions}
    if payload.task_name not in declared:
        raise HTTPException(status_code=422, detail=f"该平台不支持任务: {payload.task_name}")

    duplicate = await session.scalar(
        select(ScheduledTask.id)
        .where(
            ScheduledTask.account_id == payload.account_id,
            ScheduledTask.task_name == payload.task_name,
        )
        .limit(1)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="该账号已存在同名任务")

    try:
        parse_hhmm(payload.time_of_day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.interval_days < 1:
        raise HTTPException(status_code=422, detail="执行周期必须 ≥ 1 天")

    task = ScheduledTask(
        account_id=payload.account_id,
        task_name=payload.task_name,
        time_of_day=payload.time_of_day,
        interval_days=payload.interval_days,
        params=payload.params,
        enabled=payload.enabled,
    )
    session.add(task)
    await session.flush()
    return _task_detail(task, account)


@router.post("/{task_id}/run-now")
async def run_task_now(task_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Enqueue one execution immediately (subject to business-date dedupe)."""
    task = await session.get(ScheduledTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    account = await session.get(Account, task.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    plugin = plugin_registry.get(account.instance.platform_id)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail=f"平台插件未加载: {account.instance.platform_id}"
        )
    declared = {task_def.name for task_def in plugin.task_definitions}
    if task.task_name not in declared:
        raise HTTPException(status_code=422, detail=f"该平台不支持任务: {task.task_name}")

    execution = await create_execution(
        session,
        account,
        task.task_name,
        scheduled_task_id=task.id,
        params=task.params,
        due_at=now_utc(),
    )
    if execution is None:
        return {
            "created": False,
            "execution_id": None,
            "message": "今日已存在待执行/进行中/已成功的执行记录，跳过重复创建",
        }
    return {"created": True, "execution_id": execution.id, "message": "已加入执行队列"}


class UpdateScheduledTaskRequest(BaseModel):
    time_of_day: str | None = None
    interval_days: int | None = None
    params: dict | None = None
    enabled: bool | None = None


async def _load_task_with_account(
    task_id: int, session: AsyncSession
) -> tuple[ScheduledTask, Account]:
    task = await session.get(ScheduledTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    account = await session.get(Account, task.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return task, account


@router.put("/{task_id}")
async def update_scheduled_task(
    task_id: int, payload: UpdateScheduledTaskRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Update schedule fields; next_run_at is reset so the scheduler recomputes."""
    task, account = await _load_task_with_account(task_id, session)

    if payload.time_of_day is not None:
        try:
            parse_hhmm(payload.time_of_day)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        task.time_of_day = payload.time_of_day
    if payload.interval_days is not None:
        if payload.interval_days < 1:
            raise HTTPException(status_code=422, detail="执行周期必须 ≥ 1 天")
        task.interval_days = payload.interval_days
    if payload.params is not None:
        task.params = payload.params
    if payload.enabled is not None:
        task.enabled = payload.enabled

    task.next_run_at = None  # 让调度器按新配置重新计算
    await session.commit()
    await session.refresh(task)
    return _task_detail(task, account)


@router.delete("/{task_id}")
async def delete_scheduled_task(task_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Delete the schedule; execution history is preserved (task reference nulled)."""
    task, _account = await _load_task_with_account(task_id, session)

    await session.execute(
        update(TaskExecution)
        .where(TaskExecution.scheduled_task_id == task_id)
        .values(scheduled_task_id=None)
        .execution_options(synchronize_session=False)
    )
    await session.delete(task)
    await session.commit()
    return {"ok": True}
