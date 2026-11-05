"""MCP Server（dailykeeper_mcp 包）测试。

- 集成：BackendClient 通过 ASGITransport 依赖注入打到真实 ASGI 应用
  （与 test_local_agent 同款打法），验证总览/重登录、账号+任务+执行+资源
  完整闭环、run-now 幂等去重与静态令牌失效报错。
- 单元：DK_MCP_* 配置校验。
不启动子进程，不依赖真实网络。
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient as HttpxAsyncClient

from dailykeeper_mcp.backend import BackendClient
from dailykeeper_mcp.config import McpConfig, load_config

from app.core.config import get_settings
from app.core.security import get_cipher
from app.services.plugin_runtime import run_execution
from app.services.task_engine import claim_pending

from tests.conftest import create_demo_account


def _mcp_backend(*, token: str = "", username: str = "", password: str = "") -> BackendClient:
    """基于 ASGITransport 的 BackendClient（依赖注入，不走真实网络）。"""
    from app import main as app_main

    config = McpConfig(
        server_url="http://test", username=username, password=password, token=token
    )
    http = HttpxAsyncClient(transport=ASGITransport(app=app_main.app), base_url="http://test")
    return BackendClient(config, http_client=http)


def _admin_credentials() -> tuple[str, str]:
    settings = get_settings()
    return settings.admin_username, settings.admin_password


# ---------- 集成：总览与令牌重登录 ----------


async def test_overview_and_relogin(client):
    """用户名密码登录换取总览；令牌失效后自动重新登录并重试。"""
    username, password = _admin_credentials()
    backend = _mcp_backend(username=username, password=password)
    try:
        overview = await backend.overview()
        assert overview["app_name"]
        assert isinstance(overview["accounts"], int)
        assert isinstance(overview["executions_today"], int)
        assert "scheduler_heartbeat" in overview

        # 模拟令牌过期：下次请求 401 → 清令牌重登录 → 重试成功
        backend._token = "invalid"
        again = await backend.overview()
        assert again["app_name"] == overview["app_name"]
    finally:
        await backend.aclose()


# ---------- 集成：账号 / 任务 / 执行 / 资源闭环 ----------


async def test_accounts_and_resources_flow(client, auth_headers, session_factory):
    """建号 → MCP 客户端查账号 → run-now → PENDING → 认领执行 → SUCCESS → 资源快照。"""
    account = await create_demo_account(
        client, auth_headers, behavior="success", balance=88.5
    )
    username, password = _admin_credentials()
    backend = _mcp_backend(username=username, password=password)
    try:
        # 账号可见：平台、凭据元信息
        accounts = await backend.accounts()
        mine = [item for item in accounts if item["id"] == account["id"]]
        assert len(mine) == 1
        assert mine[0]["platform_id"] == "demo"
        assert mine[0]["has_credential"] is True
        assert mine[0]["credential_kind"] == "token"

        # 管理端建定时任务 → MCP 客户端可见 → run-now 触发
        resp = await client.post(
            "/api/scheduled-tasks",
            json={"account_id": account["id"], "task_name": "daily_checkin", "time_of_day": "10:00"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["id"]
        tasks = await backend.scheduled_tasks()
        assert any(task["id"] == task_id for task in tasks)

        run = await backend.run_task_now(task_id)
        assert run["created"] is True
        execution_id = run["execution_id"]
        assert execution_id is not None

        # 执行记录：PENDING 可查，单条详情也可见
        pending = await backend.executions(status="PENDING", limit=50)
        assert any(item["id"] == execution_id for item in pending)
        assert any(
            item["account_id"] == account["id"]
            for item in await backend.executions(account_id=account["id"], limit=50)
        )

        # 服务层认领 + 执行（与 test_engine 同款）
        async with session_factory() as session:
            claimed = await claim_pending(session, "mcp-worker", 10)
            await session.commit()
        assert execution_id in [item.id for item in claimed]
        settings = get_settings()
        await run_execution(
            execution_id,
            session_factory=session_factory,
            cipher=get_cipher(settings),
            settings=settings,
        )

        # 执行记录：SUCCESS 且结果消息/状态完整
        success = await backend.executions(status="SUCCESS", account_id=account["id"])
        match = [item for item in success if item["id"] == execution_id]
        assert len(match) == 1
        assert match[0]["result"]["status"] == "SUCCESS"
        detail = await backend.execution(execution_id)
        assert detail["status"] == "SUCCESS"
        assert detail["result"]["success"] is True
        assert detail["result"]["message"]

        # 资源快照：余额 88.5 CNY
        summary = await backend.resources_summary()
        balance = [
            item
            for item in summary
            if item["account_id"] == account["id"] and item["resource_type"] == "balance"
        ]
        assert len(balance) == 1
        assert balance[0]["value"] == 88.5
        assert balance[0]["unit"] == "CNY"
    finally:
        await backend.aclose()


async def test_run_now_dedupe(client, auth_headers):
    """幂等去重：同一天第二次 run-now 返回 created=False。"""
    account = await create_demo_account(client, auth_headers)
    resp = await client.post(
        "/api/scheduled-tasks",
        json={"account_id": account["id"], "task_name": "daily_checkin", "time_of_day": "09:30"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]

    username, password = _admin_credentials()
    backend = _mcp_backend(username=username, password=password)
    try:
        first = await backend.run_task_now(task_id)
        assert first["created"] is True
        second = await backend.run_task_now(task_id)
        assert second["created"] is False
        assert second["execution_id"] is None
        assert second["message"]
    finally:
        await backend.aclose()


# ---------- 集成：静态令牌失效 ----------


async def test_auth_error_without_credentials(client):
    """静态令牌无效且无用户名密码 → RuntimeError“认证失败”。"""
    backend = _mcp_backend(token="definitely-wrong-token")
    try:
        with pytest.raises(RuntimeError, match="认证失败"):
            await backend.overview()
    finally:
        await backend.aclose()


# ---------- 单元：配置 ----------


def test_load_config_missing_env(monkeypatch):
    """DK_MCP_TOKEN 与 DK_MCP_USERNAME/DK_MCP_PASSWORD 都缺失 → 中文 ValueError。"""
    for name in ("DK_MCP_SERVER_URL", "DK_MCP_TOKEN", "DK_MCP_USERNAME", "DK_MCP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="DK_MCP"):
        load_config()


def test_load_config_from_env(monkeypatch):
    """环境变量解析：server_url 去尾部斜杠、静态令牌模式可用。"""
    monkeypatch.setenv("DK_MCP_SERVER_URL", "https://dk.example.com/")
    monkeypatch.setenv("DK_MCP_TOKEN", f"tok-{uuid.uuid4().hex[:8]}")
    for name in ("DK_MCP_USERNAME", "DK_MCP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    config = load_config()
    assert config.server_url == "https://dk.example.com"
    assert config.token.startswith("tok-")
    assert config.request_timeout == 60.0
