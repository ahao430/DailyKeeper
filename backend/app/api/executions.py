"""Task execution history: list and detail with structured results."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.models import Account, TaskExecution, TaskResultRecord

router = APIRouter(
    prefix="/api/executions", tags=["executions"], dependencies=[Depends(get_current_admin)]
)


def _dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601; None stays None."""
    return value.isoformat() if value is not None else None


def _result_detail(record: TaskResultRecord | None) -> dict | None:
    if record is None:
        return None
    return {
        "success": record.success,
        "status": record.status,
        "message": record.message,
        "data": record.data,
        "metrics": record.metrics,
    }


def _execution_detail(
    execution: TaskExecution, account: Account, record: TaskResultRecord | None
) -> dict:
    """Serialize one execution (its account relationships must be loaded)."""
    return {
        "id": execution.id,
        "account_id": execution.account_id,
        "account_name": account.name,
        "platform_id": account.instance.platform_id,
        "instance_name": account.instance.name,
        "task_name": execution.task_name,
        "business_date": execution.business_date.isoformat(),
        "status": execution.status,
        "retries": execution.retries,
        "worker_id": execution.worker_id,
        "due_at": _dt(execution.due_at),
        "started_at": _dt(execution.started_at),
        "finished_at": _dt(execution.finished_at),
        "created_at": _dt(execution.created_at),
        "result": _result_detail(record),
    }


@router.get("")
async def list_executions(
    status: str | None = Query(None),
    account_id: int | None = Query(None),
    task_name: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Recent executions, newest first, with their structured results."""
    query = (
        select(TaskExecution, TaskResultRecord, Account)
        .join(Account, TaskExecution.account_id == Account.id)
        .outerjoin(TaskResultRecord, TaskResultRecord.execution_id == TaskExecution.id)
    )
    if status is not None:
        query = query.where(TaskExecution.status == status)
    if account_id is not None:
        query = query.where(TaskExecution.account_id == account_id)
    if task_name is not None:
        query = query.where(TaskExecution.task_name == task_name)

    rows = (
        await session.execute(
            query.order_by(TaskExecution.id.desc()).limit(limit).offset(offset)
        )
    ).all()
    return [_execution_detail(execution, account, record) for execution, record, account in rows]


@router.get("/{execution_id}")
async def get_execution(execution_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    row = await session.execute(
        select(TaskExecution, TaskResultRecord, Account)
        .join(Account, TaskExecution.account_id == Account.id)
        .outerjoin(TaskResultRecord, TaskResultRecord.execution_id == TaskExecution.id)
        .where(TaskExecution.id == execution_id)
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    execution, record, account = result
    return _execution_detail(execution, account, record)
