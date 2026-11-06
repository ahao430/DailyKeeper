"""Regression: deleting an account with executions + linked snapshots must not 500.

历史 bug：删除顺序先删 task_executions，但 resource_snapshots.execution_id
仍引用这些执行行，SQLite 外键检查直接报 FOREIGN KEY constraint failed。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.timeutil import now_utc
from app.models import (
    Account,
    Credential,
    ResourceSnapshot,
    ScheduledTask,
    TaskExecution,
    TaskResultRecord,
)
from tests.conftest import create_demo_account


@pytest.mark.asyncio
async def test_delete_account_cascades_all_references(client, auth_headers, session_factory):
    account = await create_demo_account(client, auth_headers, balance=10, points=5)
    account_id = account["id"]

    # 直接构造完整关联数据：定时任务 + 执行 + 结果 + 挂在执行上的资源快照
    async with session_factory() as session:
        session.add(
            ScheduledTask(
                account_id=account_id,
                task_name="daily_checkin",
                time_of_day="08:00",
                interval_days=1,
                enabled=True,
            )
        )
        execution = TaskExecution(
            account_id=account_id,
            task_name="daily_checkin",
            business_date=date.today(),
            status="SUCCESS",
            due_at=now_utc(),
            started_at=now_utc(),
            finished_at=now_utc(),
        )
        session.add(execution)
        await session.flush()
        execution_id = execution.id
        session.add(
            TaskResultRecord(
                execution_id=execution.id,
                success=True,
                status="SUCCESS",
                message="ok",
                data={},
                metrics={},
            )
        )
        session.add(
            ResourceSnapshot(
                account_id=account_id,
                execution_id=execution.id,  # 关键：快照同时引用账号与执行
                resource_type="balance",
                value=10,
                unit="CNY",
                observed_at=now_utc(),
                source="daily_checkin",
            )
        )
        await session.commit()

    response = await client.delete(f"/api/accounts/{account_id}", headers=auth_headers)
    assert response.status_code == 200, response.text

    async with session_factory() as session:
        assert (await session.get(Account, account_id)) is None
        assert (
            await session.scalar(select(ScheduledTask.id).where(ScheduledTask.account_id == account_id))
            is None
        )
        assert (
            await session.scalar(select(TaskExecution.id).where(TaskExecution.account_id == account_id))
            is None
        )
        assert (
            await session.scalar(select(TaskResultRecord.id).where(TaskResultRecord.execution_id == execution_id))
            is None
        )
        assert (
            await session.scalar(
                select(ResourceSnapshot.id).where(ResourceSnapshot.account_id == account_id)
            )
            is None
        )
        assert (
            await session.scalar(select(Credential.id).where(Credential.account_id == account_id))
            is None
        )
