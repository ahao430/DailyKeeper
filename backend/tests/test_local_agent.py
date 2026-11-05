"""阶段 5b：本地 Agent（dailykeeper_agent 包）测试。

- 集成：走真实 ASGI 应用 + 真实本地 demo 插件，验证
  管理端建号拿令牌 → AgentClient 心跳/认领/取上下文 → AgentRunner
  本地执行 → post_result 回传 → 管理端执行历史可见 SUCCESS 的完整闭环。
- 单元：配置缺失报错、凭据脱敏、任务超时、插件/任务缺失兜底。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient as HttpxAsyncClient

from dailykeeper_sdk import (
    PlatformPlugin,
    TaskContext,
    TaskDefinition,
    TaskResult,
)
from dailykeeper_sdk.registry import plugin_registry

from dailykeeper_agent.client import AgentClient
from dailykeeper_agent.config import AgentConfig, load_config
from dailykeeper_agent.runner import AgentRunner

from tests.conftest import create_demo_account

_AGENT_ECHO = "hi"


@pytest.fixture()
def registry_snapshot():
    """测试内直接注册的假插件用完后还原注册表，避免影响其他用例。"""
    snapshot = plugin_registry.all()
    yield plugin_registry
    plugin_registry._plugins.clear()  # noqa: SLF001 - 测试还原专用
    plugin_registry._plugins.update(snapshot)


def _agent_config(token: str) -> AgentConfig:
    return AgentConfig(server_url="http://test", token=token)


def _asgi_client(token: str) -> AgentClient:
    """基于 ASGITransport 的 AgentClient（依赖注入，不走真实网络）。"""
    from app import main as app_main

    config = _agent_config(token)
    http = HttpxAsyncClient(transport=ASGITransport(app=app_main.app), base_url="http://test")
    return AgentClient(config, http_client=http)


async def _create_agent(client, auth_headers) -> dict:
    """管理端注册 Agent，返回 {id, name, token}（令牌仅此一次可见）。"""
    resp = await client.post(
        "/api/agents",
        json={"name": f"local-agent-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _enqueue_agent_probe(client, auth_headers, account_id: int) -> int:
    """创建 agent_probe 定时任务并立即执行，返回 execution_id。"""
    resp = await client.post(
        "/api/scheduled-tasks",
        json={"account_id": account_id, "task_name": "agent_probe", "time_of_day": "10:30"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["id"]
    resp = await client.post(f"/api/scheduled-tasks/{task_id}/run-now", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] is True, body
    return body["execution_id"]


# ---------- 集成：完整闭环 ----------


async def test_local_agent_end_to_end_flow(client, auth_headers):
    """管理端准备 → Agent 心跳/认领/取上下文 → 本地插件执行 → 回传 → 历史可见。"""
    agent = await _create_agent(client, auth_headers)
    agent_client = _asgi_client(agent["token"])
    try:
        # 心跳：ok + 服务器建议的心跳间隔
        hb = await agent_client.heartbeat(version="0.1.0", capabilities=["http"])
        assert hb["ok"] is True
        assert hb["heartbeat_interval_seconds"] == 30
        assert hb["server_time"]

        # demo 账号（conftest 助手）+ 补充 agent_echo 配置 → agent_probe 立即执行
        account = await create_demo_account(client, auth_headers)
        resp = await client.put(
            f"/api/accounts/{account['id']}",
            json={"config": {"behavior": "success", "agent_echo": _AGENT_ECHO}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        execution_id = await _enqueue_agent_probe(client, auth_headers, account["id"])

        # 认领：至少包含本用例的执行，字段齐全
        tasks = await agent_client.claim_tasks(limit=5)
        mine = [t for t in tasks if t["id"] == execution_id]
        assert len(mine) == 1
        assert mine[0]["platform_id"] == "demo"
        assert mine[0]["task_name"] == "agent_probe"
        assert mine[0]["timeout_seconds"] > 0

        # 上下文：配置含 agent_echo，凭据为创建时的明文
        context = await agent_client.task_context(execution_id)
        assert context["execution_id"] == execution_id
        assert context["platform_id"] == "demo"
        assert context["config"]["agent_echo"] == _AGENT_ECHO
        assert context["credentials"]["token"] == "test-token-1234567890"

        # 本地执行：真实调用本机安装的 demo 插件
        payload = await AgentRunner(_agent_config(agent["token"])).execute(context)
        assert payload["success"] is True
        assert payload["status"] == "SUCCESS"
        assert f"Agent 探针成功: {_AGENT_ECHO}" in payload["message"]
        assert payload["data"]["echo"] == _AGENT_ECHO

        # 回传：终结为 SUCCESS
        reply = await agent_client.post_result(execution_id, payload)
        assert reply == {"ok": True, "final_status": "SUCCESS"}

        # 管理端执行历史可见成功结果
        resp = await client.get(f"/api/executions/{execution_id}", headers=auth_headers)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["status"] == "SUCCESS"
        assert f"Agent 探针成功: {_AGENT_ECHO}" in detail["result"]["message"]

        # 错误路径：不存在的执行 → RuntimeError 携带服务器 detail
        with pytest.raises(RuntimeError, match="执行记录不存在"):
            await agent_client.task_context(999999)
    finally:
        await agent_client.aclose()
        await client.delete(f"/api/agents/{agent['id']}", headers=auth_headers)


async def test_agent_client_rejects_bad_token(client, auth_headers):
    """令牌无效：所有 Agent 接口 401，客户端转为带 detail 的 RuntimeError。"""
    agent_client = _asgi_client("definitely-wrong-token")
    try:
        with pytest.raises(RuntimeError, match="Agent 令牌无效"):
            await agent_client.heartbeat(version="0.1.0", capabilities=["http"])
    finally:
        await agent_client.aclose()


# ---------- 单元：配置 ----------


async def test_load_config_missing_env(monkeypatch):
    """缺少 DK_AGENT_SERVER / DK_AGENT_TOKEN → 中文 ValueError 并列出变量名。"""
    monkeypatch.delenv("DK_AGENT_SERVER", raising=False)
    monkeypatch.delenv("DK_AGENT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="DK_AGENT"):
        load_config()


async def test_load_config_from_env_and_overrides(monkeypatch):
    """环境变量解析 + CLI 显式参数优先 + server_url 去尾部斜杠。"""
    monkeypatch.setenv("DK_AGENT_SERVER", "http://localhost:8000/")
    monkeypatch.setenv("DK_AGENT_TOKEN", "tok-1234567890")
    monkeypatch.setenv("DK_AGENT_POLL_SECONDS", "2.5")
    monkeypatch.setenv("DK_AGENT_TASK_CONCURRENCY", "3")
    monkeypatch.setenv("DK_AGENT_VERIFY_TLS", "0")
    monkeypatch.setenv("DK_AGENT_TIMEOUT_SECONDS", "120")

    config = load_config()
    assert config.server_url == "http://localhost:8000"
    assert config.token == "tok-1234567890"
    assert config.poll_seconds == 2.5
    assert config.task_concurrency == 3
    assert config.verify_tls is False
    assert config.timeout_seconds == 120

    # 显式参数（CLI）覆盖环境变量
    config = load_config(server_url="https://dk.example.com", token="cli-token")
    assert config.server_url == "https://dk.example.com"
    assert config.token == "cli-token"


# ---------- 单元：执行器兜底与脱敏 ----------


class _LeakyPlugin(PlatformPlugin):
    """抛出的异常消息携带凭据，用于验证脱敏。"""

    plugin_id = "leaky"
    plugin_name = "凭据泄漏测试插件"
    description = "抛出携带凭据的异常"
    auth_types = ["none"]
    task_definitions = [TaskDefinition(name="boom", description="抛异常", requires_agent=True)]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        raise RuntimeError(
            f"请求失败(500): Authorization: Bearer {context.credentials['access_token']}"
        )


class _SlowPlugin(PlatformPlugin):
    """永远不返回的插件，用于验证任务超时。"""

    plugin_id = "slowpoke"
    plugin_name = "超时测试插件"
    description = "模拟卡死任务"
    auth_types = ["none"]
    task_definitions = [TaskDefinition(name="hang", description="卡死", requires_agent=True)]

    async def execute(self, task_name: str, context: TaskContext) -> TaskResult:
        await asyncio.sleep(30)
        return TaskResult.ok()


async def test_runner_scrubs_credentials_in_exception(registry_snapshot):
    """插件异常：消息中的凭据值（≥8 字符）被替换为 ***，状态 FAILED 不抛出。"""
    plugin_registry.register(_LeakyPlugin)
    secret = "super-secret-access-token-42"
    runner = AgentRunner(_agent_config("t"))

    payload = await runner.execute(
        {
            "execution_id": 7,
            "platform_id": "leaky",
            "task_name": "boom",
            "credentials": {"access_token": secret, "data": {"cookie": "sid=87654321abcd"}},
            "config": {},
            "base_url": "https://leaky.example.com",
            "http_timeout": 5,
        }
    )

    assert payload["success"] is False
    assert payload["status"] == "FAILED"
    assert secret not in payload["message"]
    assert "87654321abcd" not in payload["message"]
    assert "***" in payload["message"]
    assert "500" in payload["message"]  # 非敏感信息保留


async def test_runner_timeout_marks_failed_not_retryable(registry_snapshot):
    """任务超时：FAILED + “任务超时” + data.retryable=False，且不等满 30 秒。"""
    plugin_registry.register(_SlowPlugin)
    runner = AgentRunner(_agent_config("t"))

    payload = await asyncio.wait_for(
        runner.execute(
            {
                "execution_id": 8,
                "platform_id": "slowpoke",
                "task_name": "hang",
                "credentials": {},
                "config": {},
                "base_url": "",
                "http_timeout": 5,
                "timeout_seconds": 0.2,
            }
        ),
        timeout=5,
    )

    assert payload["success"] is False
    assert payload["status"] == "FAILED"
    assert payload["message"] == "任务超时"
    assert payload["data"] == {"retryable": False}


async def test_runner_missing_plugin_and_task():
    """本地插件未安装 / 插件不支持该任务 → FAILED 中文提示。"""
    runner = AgentRunner(_agent_config("t"))

    payload = await runner.execute(
        {"execution_id": 1, "platform_id": "no-such-platform", "task_name": "x", "credentials": {}}
    )
    assert payload["status"] == "FAILED"
    assert "本地未安装平台插件: no-such-platform" in payload["message"]

    payload = await runner.execute(
        {"execution_id": 1, "platform_id": "demo", "task_name": "no-such-task", "credentials": {}}
    )
    assert payload["status"] == "FAILED"
    assert "本地插件不支持任务" in payload["message"]


# ---------- 单元：客户端错误转换 ----------


async def test_client_error_includes_status_and_detail(client, auth_headers):
    """非 2xx 响应 → RuntimeError 格式 “服务器返回 <code>: <detail>”。"""
    agent = await _create_agent(client, auth_headers)
    agent_client = _asgi_client(agent["token"])
    try:
        with pytest.raises(RuntimeError) as excinfo:
            await agent_client.post_result(
                999999,
                {"success": True, "status": "SUCCESS", "message": "", "data": {}, "metrics": {}},
            )
        # 不存在的执行：404 + 服务器中文 detail
        assert "404" in str(excinfo.value)
        assert "执行记录不存在" in str(excinfo.value)
    finally:
        await agent_client.aclose()
        await client.delete(f"/api/agents/{agent['id']}", headers=auth_headers)
