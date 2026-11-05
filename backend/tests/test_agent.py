"""本地 Agent 链路集成测试：注册/令牌 → 心跳 → 认领 → 上下文 → 结果上报，
以及离线清扫、删除中断、令牌轮换与归属校验。

主流程走 HTTP 层（管理员 JWT + Agent 令牌两种认证），数据库断言使用独立
会话。每个用例自建 Agent 与账号，互不影响；所有认领的执行都会被终结，
不遗留 RUNNING 行（避免影响 test_engine 的重启恢复用例）。
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.timeutil import now_utc
from app.models import Account, Agent, NotificationRecord, TaskExecution, TaskResultRecord
from app.services.scheduler_service import scan_and_enqueue
from app.services.task_engine import claim_pending

from tests.conftest import get_or_create_demo_instance

_TEST_CREDENTIAL_TOKEN = "agent-token-1234567890"


# ---------- 小工具 ----------


async def _create_agent(client, auth_headers, name: str | None = None) -> dict:
    """注册 Agent，返回 {id, token, ...}（令牌仅创建响应中可见）。"""
    resp = await client.post(
        "/api/agents",
        json={"name": name or f"agent-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]
    return body


async def _heartbeat(client, token: str, *, version: str = "0.0.1-test") -> dict:
    resp = await client.post(
        "/api/agent/heartbeat",
        json={"version": version, "capabilities": ["shell", "desktop"]},
        headers={"X-Agent-Token": token},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_agent_account(client, auth_headers, *, echo: str = "hello") -> dict:
    """在演示实例下创建带 agent_echo 配置的账号，返回 API 字典。"""
    instance_id = await get_or_create_demo_instance(client, auth_headers)
    resp = await client.post(
        "/api/accounts",
        json={
            "instance_id": instance_id,
            "name": f"acct-{uuid.uuid4().hex[:10]}",
            "display_name": "Agent 测试账号",
            "config": {"behavior": "success", "agent_echo": echo},
            "credential": {"kind": "token", "data": {"token": _TEST_CREDENTIAL_TOKEN}},
        },
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

    resp = await client.post(
        f"/api/scheduled-tasks/{task_id}/run-now", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] is True, body
    return body["execution_id"]


async def _claim_via_agent(client, token: str, limit: int = 2) -> list[dict]:
    resp = await client.post(
        "/api/agent/tasks/claim",
        json={"limit": limit},
        headers={"X-Agent-Token": token},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _execution(session_factory, execution_id: int) -> TaskExecution:
    async with session_factory() as session:
        return await session.get(TaskExecution, execution_id)


async def _result_of(session_factory, execution_id: int) -> TaskResultRecord | None:
    async with session_factory() as session:
        return await session.scalar(
            select(TaskResultRecord).where(TaskResultRecord.execution_id == execution_id)
        )


async def _agent_row(session_factory, agent_id: int) -> Agent:
    async with session_factory() as session:
        return await session.get(Agent, agent_id)


async def _max_notification_id(session_factory) -> int:
    async with session_factory() as session:
        value = await session.scalar(select(func.max(NotificationRecord.id)))
        return int(value) if value is not None else 0


# ---------- 测试用例 ----------


async def test_agent_lifecycle_and_task_flow(client, auth_headers, session_factory):
    """E2E：注册 → 令牌认证 → 心跳上线 → 入队分流 → 认领 → 上下文 → 结果。"""
    # 1. 管理员创建 Agent：令牌仅返回一次
    agent = await _create_agent(client, auth_headers)
    assert agent["note"]

    # 重名冲突
    resp = await client.post(
        "/api/agents", json={"name": agent["name"]}, headers=auth_headers
    )
    assert resp.status_code == 409

    # Agent 路由不要求管理员 JWT；错误令牌 → 401
    resp = await client.post(
        "/api/agent/heartbeat",
        json={},
        headers={"X-Agent-Token": "totally-wrong-token"},
    )
    assert resp.status_code == 401

    # 2. 心跳 → ONLINE，返回间隔与服务器时间
    hb = await _heartbeat(client, agent["token"])
    assert hb["ok"] is True
    assert hb["heartbeat_interval_seconds"] == 30
    assert hb["server_time"]

    row = await _agent_row(session_factory, agent["id"])
    assert row.status == "ONLINE"
    assert row.last_heartbeat is not None
    assert row.version == "0.0.1-test"
    assert row.meta["capabilities"] == ["shell", "desktop"]

    # 3. 创建账号 + agent_probe 任务并立即执行 → PENDING needs_agent
    account = await _create_agent_account(client, auth_headers)
    execution_id = await _enqueue_agent_probe(client, auth_headers, account["id"])

    execution = await _execution(session_factory, execution_id)
    assert execution.status == "PENDING"
    assert execution.needs_agent is True

    # 4. HTTP 执行线（browser=False）认领不到 Agent 通道任务
    async with session_factory() as session:
        claimed = await claim_pending(session, "w-http", 10)
        await session.commit()
    assert execution_id not in [item.id for item in claimed]

    # 5. Agent 认领 → RUNNING 且分配给该 Agent
    tasks = await _claim_via_agent(client, agent["token"])
    mine = [item for item in tasks if item["id"] == execution_id]
    assert len(mine) == 1
    assert mine[0]["task_name"] == "agent_probe"
    assert mine[0]["platform_id"] == "demo"
    assert mine[0]["timeout_seconds"] > 0

    execution = await _execution(session_factory, execution_id)
    assert execution.status == "RUNNING"
    assert execution.assigned_agent_id == agent["id"]
    assert execution.worker_id == f"agent-{agent['id']}"

    # 6. 上下文：凭据为创建时的明文，配置含 agent_echo
    resp = await client.get(
        f"/api/agent/tasks/{execution_id}/context",
        headers={"X-Agent-Token": agent["token"]},
    )
    assert resp.status_code == 200, resp.text
    context = resp.json()
    assert context["platform_id"] == "demo"
    assert context["task_name"] == "agent_probe"
    assert context["credentials"]["token"] == _TEST_CREDENTIAL_TOKEN
    assert context["config"]["agent_echo"] == "hello"
    assert context["http_timeout"] > 0

    # 7. 无效状态 → 422；随后正常上报成功结果
    resp = await client.post(
        f"/api/agent/tasks/{execution_id}/result",
        json={"success": True, "status": "BOGUS"},
        headers={"X-Agent-Token": agent["token"]},
    )
    assert resp.status_code == 422

    resp = await client.post(
        f"/api/agent/tasks/{execution_id}/result",
        json={
            "success": True,
            "status": "SUCCESS",
            "message": "Agent 探针成功: hello",
            "data": {"echo": "hello"},
        },
        headers={"X-Agent-Token": agent["token"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "final_status": "SUCCESS"}

    # 8. 执行历史可见成功结果；agent_probe 不回写签到日期
    resp = await client.get(
        f"/api/executions/{execution_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "SUCCESS"
    assert detail["result"]["message"] == "Agent 探针成功: hello"

    async with session_factory() as session:
        account_row = await session.get(Account, account["id"])
    assert account_row.last_checkin_date is None

    # 9. 管理端列表：该 Agent 在线且无运行中任务
    resp = await client.get("/api/agents", headers=auth_headers)
    assert resp.status_code == 200
    listed = {item["id"]: item for item in resp.json()}
    assert listed[agent["id"]]["status"] == "ONLINE"
    assert listed[agent["id"]]["online"] is True
    assert listed[agent["id"]]["running_tasks"] == 0

    # 未认证访问管理端 → 401
    resp = await client.get("/api/agents")
    assert resp.status_code == 401


async def test_agent_offline_sweep(client, auth_headers, session_factory):
    """心跳超时：调度扫描将 Agent 标记离线，中断其运行中执行并记录通知。"""
    before_notification = await _max_notification_id(session_factory)

    agent = await _create_agent(client, auth_headers)
    await _heartbeat(client, agent["token"])

    # 直接把心跳拨回 120 秒前（超过 90 秒离线窗口）
    async with session_factory() as session:
        row = await session.get(Agent, agent["id"])
        row.last_heartbeat = now_utc() - timedelta(seconds=120)
        await session.commit()

    account = await _create_agent_account(client, auth_headers)
    execution_id = await _enqueue_agent_probe(client, auth_headers, account["id"])
    tasks = await _claim_via_agent(client, agent["token"])
    assert execution_id in [item["id"] for item in tasks]

    async with session_factory() as session:
        await scan_and_enqueue(session)

    row = await _agent_row(session_factory, agent["id"])
    assert row.status == "OFFLINE"

    execution = await _execution(session_factory, execution_id)
    assert execution.status == "INTERRUPTED"
    assert execution.finished_at is not None

    record = await _result_of(session_factory, execution_id)
    assert record is not None
    assert record.success is False
    assert record.status == "INTERRUPTED"
    assert record.message == "Agent 离线超时，任务中断"

    # 通知：agent_offline 事件默认启用，无渠道 → SKIPPED 记录仍存在
    async with session_factory() as session:
        notifications = (
            await session.scalars(
                select(NotificationRecord)
                .where(
                    NotificationRecord.id > before_notification,
                    NotificationRecord.event == "agent_offline",
                )
                .order_by(NotificationRecord.id)
            )
        ).all()
    assert len(notifications) == 1
    assert notifications[0].status == "SKIPPED"
    assert agent["name"] in notifications[0].body


async def test_agent_delete_interrupts_running(client, auth_headers, session_factory):
    """删除 Agent：其运行中执行标记中断并解除引用，Agent 行删除。"""
    agent = await _create_agent(client, auth_headers)
    account = await _create_agent_account(client, auth_headers)
    execution_id = await _enqueue_agent_probe(client, auth_headers, account["id"])
    tasks = await _claim_via_agent(client, agent["token"])
    assert execution_id in [item["id"] for item in tasks]

    resp = await client.delete(f"/api/agents/{agent['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    execution = await _execution(session_factory, execution_id)
    assert execution.status == "INTERRUPTED"
    assert execution.assigned_agent_id is None

    record = await _result_of(session_factory, execution_id)
    assert record is not None
    assert record.status == "INTERRUPTED"
    assert record.message == "Agent 已被删除，任务中断"

    assert await _agent_row(session_factory, agent["id"]) is None

    # 重复删除 → 404
    resp = await client.delete(f"/api/agents/{agent['id']}", headers=auth_headers)
    assert resp.status_code == 404


async def test_agent_rotate(client, auth_headers):
    """令牌轮换：旧令牌立即失效，新令牌可正常心跳。"""
    agent = await _create_agent(client, auth_headers)

    resp = await client.post(f"/api/agents/{agent['id']}/rotate", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    new_token = resp.json()["token"]
    assert new_token and new_token != agent["token"]

    resp = await client.post(
        "/api/agent/heartbeat",
        json={},
        headers={"X-Agent-Token": agent["token"]},
    )
    assert resp.status_code == 401

    resp = await client.post(
        "/api/agent/heartbeat",
        json={},
        headers={"X-Agent-Token": new_token},
    )
    assert resp.status_code == 200


async def test_agent_result_ownership(client, auth_headers, session_factory):
    """归属校验：其他 Agent 获取上下文/上报结果 → 403；执行仍归属原 Agent。"""
    agent_a = await _create_agent(client, auth_headers)
    agent_b = await _create_agent(client, auth_headers)

    account = await _create_agent_account(client, auth_headers)
    execution_id = await _enqueue_agent_probe(client, auth_headers, account["id"])
    tasks = await _claim_via_agent(client, agent_a["token"])
    assert execution_id in [item["id"] for item in tasks]

    # B 的认领为空（无待领任务）
    assert await _claim_via_agent(client, agent_b["token"]) == []

    resp = await client.get(
        f"/api/agent/tasks/{execution_id}/context",
        headers={"X-Agent-Token": agent_b["token"]},
    )
    assert resp.status_code == 403

    resp = await client.post(
        f"/api/agent/tasks/{execution_id}/result",
        json={"success": True, "status": "SUCCESS"},
        headers={"X-Agent-Token": agent_b["token"]},
    )
    assert resp.status_code == 403

    # 不存在的执行 → 404
    resp = await client.get(
        "/api/agent/tasks/999999/context",
        headers={"X-Agent-Token": agent_a["token"]},
    )
    assert resp.status_code == 404

    # 原归属者仍可正常终结执行（不留 RUNNING 残留）
    resp = await client.post(
        f"/api/agent/tasks/{execution_id}/result",
        json={"success": False, "status": "FAILED", "message": "演示失败"},
        headers={"X-Agent-Token": agent_a["token"]},
    )
    assert resp.status_code == 200
    assert resp.json()["final_status"] == "FAILED"
