"""任务引擎集成测试：调度→入队→认领→执行→结果→通知→重试。

全部通过服务层（scheduler_service / task_engine / plugin_runtime）+ demo/mteam
插件驱动，不经过 HTTP 层。所有断言都读取全新的数据库会话，因为各服务内部
自行提交事务。
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

try:  # mteam 插件用于浏览器自动化守卫用例；缺失时跳过对应测试
    from dailykeeper_plugin_mteam.plugin import MTeamPlugin  # noqa: F401

    _MTEAM_AVAILABLE = True
except ImportError:  # pragma: no cover - 仅在插件未安装时触发
    _MTEAM_AVAILABLE = False

from app.core.config import get_settings
from app.core.security import get_cipher
from app.core.timeutil import now_utc
from app.models import (
    Account,
    Credential,
    NotificationRecord,
    PlatformInstance,
    ResourceSnapshot,
    ScheduledTask,
    TaskExecution,
    TaskResultRecord,
)
from app.services.plugin_runtime import run_execution
from app.services.scheduler_service import scan_and_enqueue
from app.services.task_engine import claim_pending, create_execution, recover_interrupted

needs_mteam = pytest.mark.skipif(not _MTEAM_AVAILABLE, reason="mteam 插件未安装")


# ---------- 构造链路的小工具（全部走 ORM，绕开 HTTP 层） ----------


async def _make_chain(
    session_factory,
    *,
    behavior: str = "success",
    balance: float = 0.0,
    with_task: bool = True,
    time_of_day: str = "08:30",
    platform_id: str = "demo",
) -> dict:
    """Create instance + account (+ credential + scheduled task); return ids."""
    async with session_factory() as session:
        instance = PlatformInstance(
            platform_id=platform_id,
            name=f"inst-{uuid.uuid4().hex[:6]}",
            base_url="",
            config={},
        )
        session.add(instance)
        await session.flush()

        account = Account(
            instance_id=instance.id,
            name=f"acct-{uuid.uuid4().hex[:6]}",
            config={"behavior": behavior, "balance": balance, "points": 0},
        )
        session.add(account)
        await session.flush()

        cipher = get_cipher(get_settings())
        session.add(
            Credential(
                account_id=account.id,
                kind="token",
                data_encrypted=cipher.encrypt_dict({"token": "demo-token-1234567890"}),
            )
        )

        task = None
        if with_task:
            task = ScheduledTask(
                account_id=account.id,
                task_name="daily_checkin",
                time_of_day=time_of_day,
                interval_days=1,
            )
            session.add(task)

        await session.commit()
        return {
            "instance_id": instance.id,
            "account_id": account.id,
            "task_id": task.id if task is not None else None,
        }


async def _make_task_due(session_factory, task_id: int) -> None:
    """把 next_run_at 拨到过去，确保下一轮调度会入队。"""
    async with session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        task.next_run_at = now_utc() - timedelta(minutes=1)
        await session.commit()


async def _scan(session_factory) -> int:
    async with session_factory() as session:
        return await scan_and_enqueue(session)


async def _claim_all(session_factory) -> list[int]:
    """Claim every due PENDING execution as worker w1 (commit persisted)."""
    async with session_factory() as session:
        claimed = await claim_pending(session, "w1", 10)
        await session.commit()
        return [execution.id for execution in claimed]


async def _run(session_factory, execution_id: int) -> None:
    settings = get_settings()
    await run_execution(
        execution_id,
        session_factory=session_factory,
        cipher=get_cipher(settings),
        settings=settings,
    )


async def _executions_of(session_factory, account_id: int) -> list[TaskExecution]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(TaskExecution)
                .where(TaskExecution.account_id == account_id)
                .order_by(TaskExecution.id)
            )
        ).all()
        return list(rows)


async def _results_of(session_factory, execution_id: int) -> list[TaskResultRecord]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(TaskResultRecord).where(
                    TaskResultRecord.execution_id == execution_id
                )
            )
        ).all()
        return list(rows)


async def _max_notification_id(session_factory) -> int:
    async with session_factory() as session:
        value = await session.scalar(select(func.max(NotificationRecord.id)))
        return int(value) if value is not None else 0


async def _notifications_since(
    session_factory, after_id: int, event: str
) -> list[NotificationRecord]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(NotificationRecord)
                .where(NotificationRecord.id > after_id, NotificationRecord.event == event)
                .order_by(NotificationRecord.id)
            )
        ).all()
        return list(rows)


# ---------- 测试用例 ----------


async def test_full_checkin_flow(session_factory):
    """签到全流程：调度入队 → 认领 → 执行成功 → 结果/账号状态/快照/通知。"""
    before_notification = await _max_notification_id(session_factory)
    chain = await _make_chain(session_factory, behavior="success", balance=12.5)
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1
    assert executions[0].status == "PENDING"
    execution_id = executions[0].id

    claimed = await _claim_all(session_factory)
    assert claimed == [execution_id]

    await _run(session_factory, execution_id)

    execution_row = (
        await _executions_of(session_factory, chain["account_id"])
    )[0]
    assert execution_row.status == "SUCCESS"
    assert execution_row.finished_at is not None

    records = await _results_of(session_factory, execution_id)
    assert len(records) == 1
    assert records[0].success is True
    assert records[0].status == "SUCCESS"
    assert records[0].message  # 结果消息非空

    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        assert account.status == "ACTIVE"
        assert account.last_checkin_date == execution_row.business_date

    # 资源快照：余额 12.5 CNY
    async with session_factory() as session:
        snapshots = (
            await session.scalars(
                select(ResourceSnapshot).where(
                    ResourceSnapshot.account_id == chain["account_id"]
                )
            )
        ).all()
    balances = [s for s in snapshots if s.resource_type == "balance"]
    assert len(balances) == 1
    assert float(balances[0].value) == 12.5
    assert balances[0].unit == "CNY"

    # 通知：task_success 默认关闭 → 记录存在但状态为 SKIPPED（无渠道）
    notifications = await _notifications_since(
        session_factory, before_notification, "task_success"
    )
    assert len(notifications) == 1
    assert notifications[0].status == "SKIPPED"
    assert notifications[0].channels == []


async def test_dedupe_same_business_date(session_factory):
    """同一业务日期内不重复入队：再次调度/直接创建都会被去重。"""
    chain = await _make_chain(session_factory)
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1
    # 再扫一轮：next_run_at 已推进到未来；即便恰好到期，成功去重也会兜底
    assert await _scan(session_factory) == 0

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1
    execution_id = executions[0].id

    claimed = await _claim_all(session_factory)
    assert claimed == [execution_id]
    await _run(session_factory, execution_id)

    # 成功后（SUCCESS 参与去重），直接创建返回 None
    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        assert await create_execution(session, account, "daily_checkin") is None

    assert len(await _executions_of(session_factory, chain["account_id"])) == 1


async def test_auth_expired_flow(session_factory):
    """登录失效：执行状态 AUTH_EXPIRED，账号标记失效，通知被记录。"""
    before_notification = await _max_notification_id(session_factory)
    chain = await _make_chain(session_factory, behavior="auth_expired")
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1
    claimed = await _claim_all(session_factory)
    assert len(claimed) == 1
    await _run(session_factory, claimed[0])

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1
    assert executions[0].status == "AUTH_EXPIRED"

    records = await _results_of(session_factory, claimed[0])
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].status == "AUTH_EXPIRED"

    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        assert account.status == "AUTH_EXPIRED"

    # 无渠道配置 → 通知记录存在但状态为 SKIPPED
    notifications = await _notifications_since(
        session_factory, before_notification, "auth_expired"
    )
    assert len(notifications) == 1
    assert notifications[0].status == "SKIPPED"


async def test_retry_scheduling(session_factory):
    """可重试失败：原执行 FAILED，同时生成一条带退避的重试 PENDING 执行。"""
    chain = await _make_chain(session_factory, behavior="fail_retryable")
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1
    claimed = await _claim_all(session_factory)
    assert len(claimed) == 1
    await _run(session_factory, claimed[0])

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 2
    failed = [e for e in executions if e.status == "FAILED"]
    pending = [e for e in executions if e.status == "PENDING"]
    assert len(failed) == 1
    assert len(pending) == 1

    assert pending[0].retries == 1
    assert pending[0].due_at is not None
    assert pending[0].due_at > now_utc()  # 退避时间在未来

    records = await _results_of(session_factory, failed[0].id)
    assert records[0].success is False
    assert records[0].status == "FAILED"
    assert records[0].data.get("retryable") is True


async def test_rate_limited_no_auto_retry(session_factory):
    """限流：执行状态 RATE_LIMITED，引擎不自动生成重试执行。"""
    before_notification = await _max_notification_id(session_factory)
    chain = await _make_chain(session_factory, behavior="rate_limited")
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1
    claimed = await _claim_all(session_factory)
    assert len(claimed) == 1
    await _run(session_factory, claimed[0])

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1  # 没有自动重试执行
    assert executions[0].status == "RATE_LIMITED"

    records = await _results_of(session_factory, claimed[0])
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].status == "RATE_LIMITED"

    notifications = await _notifications_since(
        session_factory, before_notification, "rate_limited"
    )
    assert len(notifications) == 1
    assert notifications[0].status == "SKIPPED"


@needs_mteam
async def test_needs_action_browser_guard(session_factory):
    """浏览器守卫：mteam 的 daily_checkin 声明 requires_browser → NEEDS_ACTION。"""
    before_notification = await _max_notification_id(session_factory)
    chain = await _make_chain(session_factory, platform_id="mteam")
    await _make_task_due(session_factory, chain["task_id"])

    assert await _scan(session_factory) == 1
    claimed = await _claim_all(session_factory)
    assert len(claimed) == 1
    await _run(session_factory, claimed[0])

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1
    assert executions[0].status == "NEEDS_ACTION"

    records = await _results_of(session_factory, claimed[0])
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].status == "NEEDS_ACTION"
    assert "浏览器" in records[0].message

    # 守卫在插件执行前触发，不发起网络请求，也不修改账号状态
    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        assert account.status == "ACTIVE"

    notifications = await _notifications_since(
        session_factory, before_notification, "needs_action"
    )
    assert len(notifications) == 1
    assert notifications[0].status == "SKIPPED"

    # NEEDS_ACTION 参与业务日期去重：重新调度不再入队
    await _make_task_due(session_factory, chain["task_id"])
    assert await _scan(session_factory) == 0
    assert len(await _executions_of(session_factory, chain["account_id"])) == 1


async def test_interrupted_recovery(session_factory):
    """服务重启恢复：RUNNING 执行被标记 INTERRUPTED 并写入结果记录。"""
    chain = await _make_chain(session_factory, with_task=False)
    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        execution = await create_execution(session, account, "daily_checkin")
        await session.commit()
        execution_id = execution.id

    async with session_factory() as session:
        running = await session.get(TaskExecution, execution_id)
        running.status = "RUNNING"
        running.worker_id = "w-recover"
        await session.commit()

    async with session_factory() as session:
        recovered = await recover_interrupted(session)
    assert recovered == 1

    async with session_factory() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution.status == "INTERRUPTED"
        assert execution.finished_at is not None

    records = await _results_of(session_factory, execution_id)
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].status == "INTERRUPTED"


async def test_unknown_task(session_factory):
    """未声明任务：引擎直接判 FAILED（不可重试），不生成重试执行。"""
    chain = await _make_chain(session_factory, with_task=False)
    async with session_factory() as session:
        account = await session.get(Account, chain["account_id"])
        execution = await create_execution(session, account, "no_such_task")
        await session.commit()
        execution_id = execution.id

    claimed = await _claim_all(session_factory)
    assert claimed == [execution_id]
    await _run(session_factory, execution_id)

    executions = await _executions_of(session_factory, chain["account_id"])
    assert len(executions) == 1
    assert executions[0].status == "FAILED"

    records = await _results_of(session_factory, execution_id)
    assert len(records) == 1
    assert records[0].success is False
    assert "未知任务" in records[0].message
    assert records[0].data.get("retryable") is False
