"""浏览器 Worker 阶段测试：认领分流、误领守卫、端到端探针与调度入队打标。

不依赖浏览器二进制的用例（分流/守卫/调度）始终运行；真实的 Playwright 端
到端用例在 playwright 包或 Chromium 二进制不可用时优雅跳过。每个测试使用
独立账号，执行按（账号, 任务, 业务日期）去重，互不影响。
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - 仅在 playwright 未安装时触发
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False

from app.core.config import get_settings
from app.core.security import get_cipher
from app.core.timeutil import now_utc
from app.models import (
    Account,
    Credential,
    PlatformInstance,
    ScheduledTask,
    TaskExecution,
    TaskResultRecord,
)
from app.services.plugin_runtime import run_execution
from app.services.scheduler_service import scan_and_enqueue
from app.services.task_engine import claim_pending, create_execution

needs_playwright = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE, reason="playwright 未安装"
)


# ---------- 构造链路的小工具（与 test_engine 同一模式，全部走 ORM）


async def _make_chain(
    session_factory,
    *,
    behavior: str = "success",
    with_task: bool = True,
    task_name: str = "daily_checkin",
    task_due: bool = False,
) -> dict:
    """Create demo instance + account (+ credential + scheduled task); return ids.

    ``task_due=True`` 直接把 ``next_run_at`` 拨到过去，下一轮调度即会入队。
    """
    async with session_factory() as session:
        instance = PlatformInstance(
            platform_id="demo",
            name=f"inst-{uuid.uuid4().hex[:6]}",
            base_url="",
            config={},
        )
        session.add(instance)
        await session.flush()

        account = Account(
            instance_id=instance.id,
            name=f"acct-{uuid.uuid4().hex[:6]}",
            config={"behavior": behavior, "balance": 0, "points": 0},
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
                task_name=task_name,
                time_of_day="10:00",
                interval_days=1,
            )
            if task_due:
                task.next_run_at = now_utc() - timedelta(minutes=1)
            session.add(task)

        await session.commit()
        return {
            "instance_id": instance.id,
            "account_id": account.id,
            "task_id": task.id if task is not None else None,
        }


async def _create(
    session_factory, account_id: int, task_name: str
) -> int:
    """Create one PENDING execution for the account and return its id."""
    async with session_factory() as session:
        account = await session.get(Account, account_id)
        execution = await create_execution(session, account, task_name)
        await session.commit()
        assert execution is not None
        return execution.id


async def _claim(
    session_factory, worker_id: str, *, browser: bool = False
) -> list[TaskExecution]:
    """Claim due PENDING executions as ``worker_id`` (commit persisted)."""
    async with session_factory() as session:
        claimed = await claim_pending(session, worker_id, 10, browser=browser)
        await session.commit()
        return list(claimed)


async def _finish(session_factory, execution_ids: list[int]) -> None:
    """把执行标记为 SUCCESS，避免遗留 RUNNING 行影响其他测试。"""
    async with session_factory() as session:
        for execution_id in execution_ids:
            execution = await session.get(TaskExecution, execution_id)
            execution.status = "SUCCESS"
            execution.finished_at = now_utc()
        await session.commit()


async def _result_of(session_factory, execution_id: int) -> TaskResultRecord:
    async with session_factory() as session:
        record = await session.scalar(
            select(TaskResultRecord).where(TaskResultRecord.execution_id == execution_id)
        )
        assert record is not None
        return record


async def _execution_of(session_factory, execution_id: int) -> TaskExecution:
    async with session_factory() as session:
        execution = await session.get(TaskExecution, execution_id)
        assert execution is not None
        return execution


# ---------- 测试用例


async def test_claim_split_routing(session_factory):
    """认领分流：create_execution 按 task_def 打标，两类 worker 各领各的。"""
    chain = await _make_chain(session_factory, with_task=False)
    account_id = chain["account_id"]

    checkin_id = await _create(session_factory, account_id, "daily_checkin")
    probe_id = await _create(session_factory, account_id, "browser_probe")

    row = await _execution_of(session_factory, checkin_id)
    assert row.needs_browser is False
    row = await _execution_of(session_factory, probe_id)
    assert row.needs_browser is True

    # 普通 worker：领到 daily_checkin，领不到 browser_probe
    claimed_http = await _claim(session_factory, "w-http")
    http_ids = [e.id for e in claimed_http]
    assert [e.id for e in claimed_http if e.account_id == account_id] == [checkin_id]
    assert probe_id not in http_ids

    # browser worker：领到 browser_probe，且领到的全部是浏览器任务
    claimed_bw = await _claim(session_factory, "w-bw", browser=True)
    bw_ids = [e.id for e in claimed_bw]
    assert [e.id for e in claimed_bw if e.account_id == account_id] == [probe_id]
    assert checkin_id not in bw_ids
    assert all(e.needs_browser for e in claimed_bw)

    # 收尾：清理本轮认领的行，保持队列干净
    await _finish(session_factory, http_ids + bw_ids)


async def test_misroute_guard(session_factory):
    """误领守卫：requires_browser 任务不带浏览器会话执行 → NEEDS_ACTION。"""
    chain = await _make_chain(session_factory, with_task=False)
    probe_id = await _create(session_factory, chain["account_id"], "browser_probe")

    claimed = await _claim(session_factory, "w-bw", browser=True)
    assert [e.id for e in claimed] == [probe_id]

    settings = get_settings()
    await run_execution(
        probe_id,
        session_factory=session_factory,
        cipher=get_cipher(settings),
        settings=settings,
    )

    execution = await _execution_of(session_factory, probe_id)
    assert execution.status == "NEEDS_ACTION"
    record = await _result_of(session_factory, probe_id)
    assert record.success is False
    assert record.status == "NEEDS_ACTION"
    assert "未提供浏览器会话" in record.message


@needs_playwright
async def test_browser_probe_end_to_end(session_factory):
    """端到端：真实 Chromium 执行 browser_probe，登录状态文件落盘。"""
    from app.browser_worker.main import browser_state_path, persist_browser_state

    chain = await _make_chain(session_factory, with_task=False)
    account_id = chain["account_id"]
    probe_id = await _create(session_factory, account_id, "browser_probe")

    claimed = await _claim(session_factory, "w-bw", browser=True)
    assert [e.id for e in claimed] == [probe_id]

    settings = get_settings()
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - 浏览器二进制缺失时优雅跳过
            pytest.skip(f"Chromium 启动失败（可能未安装浏览器二进制）: {exc}")

        browser_ctx = await browser.new_context()
        page = await browser_ctx.new_page()
        try:
            await run_execution(
                probe_id,
                session_factory=session_factory,
                cipher=get_cipher(settings),
                settings=settings,
                browser_page=page,
                browser_context=browser_ctx,
            )

            execution = await _execution_of(session_factory, probe_id)
            assert execution.status == "SUCCESS"
            record = await _result_of(session_factory, probe_id)
            assert record.success is True
            assert "浏览器探针成功" in record.message
            assert "dailykeeper-probe" in record.data["title"]

            # 模拟 browser worker 收尾：持久化上下文登录状态后清理文件
            await persist_browser_state(browser_ctx, settings, account_id)
            state_path = browser_state_path(settings, account_id)
            assert Path(state_path).exists()
            os.remove(state_path)
        finally:
            await browser_ctx.close()
            await browser.close()


async def test_scheduler_enqueues_browser_task(session_factory):
    """调度打标：browser_probe 定时任务到期入队后，执行行带 needs_browser。"""
    chain = await _make_chain(
        session_factory,
        with_task=True,
        task_name="browser_probe",
        task_due=True,
    )

    async with session_factory() as session:
        assert await scan_and_enqueue(session) == 1

    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(TaskExecution).where(
                    TaskExecution.account_id == chain["account_id"]
                )
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].task_name == "browser_probe"
    assert rows[0].status == "PENDING"
    assert rows[0].needs_browser is True

    # 收尾：不留 PENDING 浏览器执行，避免干扰后续用例的全局认领断言
    await _finish(session_factory, [rows[0].id])
