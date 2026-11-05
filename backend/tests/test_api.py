"""HTTP API 集成测试：认证、平台、账号、任务、执行、资源、系统设置。

测试按文件内定义顺序执行，依赖顺序的用例（如 bootstrap 必须在改密之前）已
按此排列；改密用例自恢复默认密码且放在最后。通知设置用例结束时恢复为无渠
道配置，避免影响后续引擎测试的通知断言（pytest 按文件名字母序收集，
test_api 先于 test_engine 运行）。
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import get_cipher
from app.models import Credential
from app.services.plugin_runtime import run_execution
from app.services.task_engine import claim_pending

from tests.conftest import create_demo_account, get_or_create_demo_instance


# ---------- 小工具 ----------


async def _create_account(client, auth_headers, instance_id: int, **overrides) -> dict:
    """在指定实例下创建账号（unique 名称），返回 API 字典。"""
    payload = {
        "instance_id": instance_id,
        "name": f"acct-{uuid.uuid4().hex[:10]}",
        "config": {"behavior": "success"},
        "credential": {"kind": "token", "data": {"token": "test-token-1234567890"}},
    }
    payload.update(overrides)
    resp = await client.post("/api/accounts", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_task(client, auth_headers, account_id: int, **overrides) -> dict:
    """为账号创建每日签到定时任务，返回 API 字典。"""
    payload = {
        "account_id": account_id,
        "task_name": "daily_checkin",
        "time_of_day": "08:30",
    }
    payload.update(overrides)
    resp = await client.post("/api/scheduled-tasks", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _claim_and_run_all(session_factory, *expected_ids) -> list[int]:
    """模拟 worker：认领所有到期执行并逐个运行，返回被认领的 id 列表。"""
    async with session_factory() as session:
        claimed = await claim_pending(session, "w1", 50)
        await session.commit()
    claimed_ids = [execution.id for execution in claimed]
    if expected_ids:
        assert set(expected_ids) <= set(claimed_ids)
    settings = get_settings()
    for execution_id in claimed_ids:
        await run_execution(
            execution_id,
            session_factory=session_factory,
            cipher=get_cipher(settings),
            settings=settings,
        )
    return claimed_ids


# ---------- 认证 ----------


async def test_healthz_public(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_protected_routes_require_auth(client):
    resp = await client.get("/api/platforms")
    assert resp.status_code == 401


async def test_bootstrap_default_credentials(client):
    resp = await client.get("/api/auth/bootstrap")
    assert resp.status_code == 200
    assert resp.json()["default_credentials"] is True


async def test_login_ok(client):
    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["username"] == "admin"
    assert body["access_token"]


async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "nope"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


async def test_me(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


# ---------- 平台与平台实例 ----------


async def test_plugins_list_contains_demo(client, auth_headers):
    resp = await client.get("/api/plugins", headers=auth_headers)
    assert resp.status_code == 200
    plugins = resp.json()
    demo = next(p for p in plugins if p["plugin_id"] == "demo")
    assert demo["plugin_name"] == "演示平台"
    assert any(t["name"] == "daily_checkin" for t in demo["task_definitions"])


async def test_create_demo_instance(client, auth_headers):
    instance_id = await get_or_create_demo_instance(client, auth_headers)
    resp = await client.get(f"/api/platforms/{instance_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == instance_id
    assert body["platform_id"] == "demo"
    assert body["name"] == "演示实例"
    assert body["enabled"] is True


async def test_create_instance_unknown_platform(client, auth_headers):
    resp = await client.post(
        "/api/platforms",
        json={"platform_id": "nope", "name": "未知平台实例"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "平台插件未加载: nope"


async def test_update_platform_name(client, auth_headers):
    created = await client.post(
        "/api/platforms",
        json={"platform_id": "demo", "name": "待改名实例"},
        headers=auth_headers,
    )
    assert created.status_code == 200
    instance_id = created.json()["id"]

    resp = await client.put(
        f"/api/platforms/{instance_id}",
        json={"name": "已改名实例"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "已改名实例"


async def test_delete_platform_without_accounts(client, auth_headers):
    created = await client.post(
        "/api/platforms",
        json={"platform_id": "demo", "name": "待删除实例"},
        headers=auth_headers,
    )
    assert created.status_code == 200
    instance_id = created.json()["id"]

    resp = await client.delete(f"/api/platforms/{instance_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    missing = await client.get(f"/api/platforms/{instance_id}", headers=auth_headers)
    assert missing.status_code == 404


async def test_delete_platform_with_accounts_conflict(client, auth_headers):
    created = await client.post(
        "/api/platforms",
        json={"platform_id": "demo", "name": "有账号实例"},
        headers=auth_headers,
    )
    assert created.status_code == 200
    instance_id = created.json()["id"]
    await _create_account(client, auth_headers, instance_id)

    resp = await client.delete(f"/api/platforms/{instance_id}", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "该平台实例下仍有账号，请先删除账号"


# ---------- 账号与凭据 ----------


async def test_create_account_encrypted_credential(client, auth_headers, session_factory):
    instance_id = await get_or_create_demo_instance(client, auth_headers)
    account = await _create_account(
        client,
        auth_headers,
        instance_id,
        display_name="加密凭据测试",
        credential={"kind": "token", "data": {"token": "sk-abcdef1234567890"}},
    )
    assert account["has_credential"] is True
    assert account["credential_kind"] == "token"

    # 列表接口同样只暴露凭据元数据
    listing = await client.get("/api/accounts", headers=auth_headers)
    assert listing.status_code == 200
    match = next(a for a in listing.json() if a["id"] == account["id"])
    assert match["has_credential"] is True
    assert match["credential_kind"] == "token"

    # 数据库中凭据为 AES-GCM 密文（enc1: 前缀），不出现明文
    async with session_factory() as session:
        credential = await session.scalar(
            select(Credential).where(Credential.account_id == account["id"])
        )
    assert credential is not None
    assert credential.kind == "token"
    assert credential.data_encrypted.startswith("enc1:")
    assert "sk-abcdef1234567890" not in credential.data_encrypted


async def test_create_account_invalid_credential_kind(client, auth_headers):
    instance_id = await get_or_create_demo_instance(client, auth_headers)
    resp = await client.post(
        "/api/accounts",
        json={
            "instance_id": instance_id,
            "name": f"acct-{uuid.uuid4().hex[:10]}",
            "config": {},
            "credential": {"kind": "none", "data": {}},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "凭据类型无效: none"


async def test_account_check_success(client, auth_headers):
    account = await create_demo_account(client, auth_headers, behavior="success")
    resp = await client.post(
        f"/api/accounts/{account['id']}/check", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "SUCCESS"
    assert body["execution_id"] > 0


async def test_account_check_auth_expired(client, auth_headers):
    account = await create_demo_account(client, auth_headers, behavior="auth_expired")
    resp = await client.post(
        f"/api/accounts/{account['id']}/check", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "AUTH_EXPIRED"

    # 账号状态已同步翻转，可从 GET 接口看到
    detail = await client.get(f"/api/accounts/{account['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "AUTH_EXPIRED"


# ---------- 定时任务 ----------


async def test_scheduled_task_validation_and_duplicate(client, auth_headers):
    account = await create_demo_account(client, auth_headers)
    account_id = account["id"]

    task = await _create_task(client, auth_headers, account_id)
    assert task["next_run_at"] is not None  # 未持久化时返回预览值
    assert task["platform_id"] == "demo"
    assert task["time_of_day"] == "08:30"

    duplicate = await client.post(
        "/api/scheduled-tasks",
        json={"account_id": account_id, "task_name": "daily_checkin"},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "该账号已存在同名任务"

    # 参数校验用另一个账号（同账号同任务会先被 409 拦截）
    other = await create_demo_account(client, auth_headers)
    other_id = other["id"]

    bad_time = await client.post(
        "/api/scheduled-tasks",
        json={"account_id": other_id, "task_name": "daily_checkin", "time_of_day": "25:00"},
        headers=auth_headers,
    )
    assert bad_time.status_code == 422
    assert bad_time.json()["detail"] == "无效时间格式，应为 HH:MM"

    bad_task = await client.post(
        "/api/scheduled-tasks",
        json={"account_id": other_id, "task_name": "no_such"},
        headers=auth_headers,
    )
    assert bad_task.status_code == 422
    assert bad_task.json()["detail"] == "该平台不支持任务: no_such"

    bad_interval = await client.post(
        "/api/scheduled-tasks",
        json={
            "account_id": other_id,
            "task_name": "daily_checkin",
            "interval_days": 0,
        },
        headers=auth_headers,
    )
    assert bad_interval.status_code == 422
    assert bad_interval.json()["detail"] == "执行周期必须 ≥ 1 天"


async def test_run_now_dedupe(client, auth_headers, session_factory):
    account = await create_demo_account(client, auth_headers)
    account_id = account["id"]
    task = await _create_task(client, auth_headers, account_id)
    task_id = task["id"]

    first = await client.post(
        f"/api/scheduled-tasks/{task_id}/run-now", headers=auth_headers
    )
    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["execution_id"] is not None
    execution_id = body["execution_id"]

    second = await client.post(
        f"/api/scheduled-tasks/{task_id}/run-now", headers=auth_headers
    )
    assert second.status_code == 200
    body = second.json()
    assert body["created"] is False
    assert body["execution_id"] is None

    # 列表接口返回（预览的）下次运行时间
    listing = await client.get(
        "/api/scheduled-tasks",
        params={"account_id": account_id},
        headers=auth_headers,
    )
    assert listing.status_code == 200
    tasks = listing.json()
    assert len(tasks) == 1
    assert tasks[0]["next_run_at"] is not None

    # 模拟 worker 跑完队列，保持数据库干净（不留 PENDING 执行）
    await _claim_and_run_all(session_factory, execution_id)


# ---------- 执行记录 ----------


async def test_executions_list_and_detail(client, auth_headers, session_factory):
    account = await create_demo_account(client, auth_headers)
    account_id = account["id"]
    task = await _create_task(client, auth_headers, account_id)

    run_now = await client.post(
        f"/api/scheduled-tasks/{task['id']}/run-now", headers=auth_headers
    )
    execution_id = run_now.json()["execution_id"]

    # worker 未运行：执行停留在 PENDING，无结果记录
    pending = await client.get(f"/api/executions/{execution_id}", headers=auth_headers)
    assert pending.status_code == 200
    body = pending.json()
    assert body["status"] == "PENDING"
    assert body["result"] is None
    date.fromisoformat(body["business_date"])  # 业务日期为 ISO 字符串

    await _claim_and_run_all(session_factory, execution_id)

    detail = await client.get(f"/api/executions/{execution_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "SUCCESS"
    assert body["result"] is not None
    assert body["result"]["success"] is True
    assert body["result"]["message"]

    listing = await client.get(
        "/api/executions", params={"account_id": account_id}, headers=auth_headers
    )
    assert listing.status_code == 200
    items = listing.json()
    assert any(item["id"] == execution_id for item in items)
    assert all(isinstance(item["business_date"], str) for item in items)


# ---------- 资源快照 ----------


async def test_resources_after_successful_run(client, auth_headers, session_factory):
    account = await create_demo_account(
        client, auth_headers, behavior="success", balance=12.5
    )
    account_id = account["id"]
    task = await _create_task(client, auth_headers, account_id)

    run_now = await client.post(
        f"/api/scheduled-tasks/{task['id']}/run-now", headers=auth_headers
    )
    execution_id = run_now.json()["execution_id"]
    await _claim_and_run_all(session_factory, execution_id)

    listing = await client.get(
        "/api/resources", params={"account_id": account_id}, headers=auth_headers
    )
    assert listing.status_code == 200
    balances = [s for s in listing.json() if s["resource_type"] == "balance"]
    assert len(balances) == 1
    assert balances[0]["value"] == 12.5
    assert balances[0]["unit"] == "CNY"
    assert balances[0]["account_id"] == account_id

    summary = await client.get("/api/resources/summary", headers=auth_headers)
    assert summary.status_code == 200
    item = next(
        s
        for s in summary.json()
        if s["account_id"] == account_id and s["resource_type"] == "balance"
    )
    assert item["value"] == 12.5


# ---------- 系统信息与设置 ----------


async def test_system_info(client, auth_headers):
    resp = await client.get("/api/system/info", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_name"] == "DailyKeeper"
    assert body["database"] == "sqlite"
    assert body["plugins"] >= 1
    for key in (
        "version",
        "env",
        "instances",
        "accounts",
        "scheduled_tasks",
        "executions_today",
        "executions_today_success",
        "notifications_enabled",
        "scheduler_heartbeat",
    ):
        assert key in body


async def test_notification_settings_roundtrip(client, auth_headers):
    resp = await client.get("/api/system/settings", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["notifications"]["events"]["task_success"]["enabled"] is False
    assert body["general"]["timezone"] == "Asia/Shanghai"

    put = await client.put(
        "/api/system/settings/notifications",
        json={
            "enabled": True,
            "channels": [
                {
                    "type": "webhook",
                    "name": "测试渠道",
                    "config": {"url": "http://127.0.0.1:1/"},
                }
            ],
        },
        headers=auth_headers,
    )
    assert put.status_code == 200
    assert put.json() == {"ok": True}

    reread = await client.get("/api/system/settings", headers=auth_headers)
    channels = reread.json()["notifications"]["channels"]
    assert len(channels) == 1
    assert channels[0]["type"] == "webhook"

    # 恢复无渠道配置（引擎测试依赖默认通知行为）
    restore = await client.put(
        "/api/system/settings/notifications",
        json={"enabled": True, "channels": []},
        headers=auth_headers,
    )
    assert restore.status_code == 200


async def test_notification_test_send_dead_port(client, auth_headers):
    put = await client.put(
        "/api/system/settings/notifications",
        json={
            "enabled": True,
            "channels": [
                {
                    "type": "webhook",
                    "name": "测试渠道",
                    "config": {"url": "http://127.0.0.1:1/"},
                }
            ],
        },
        headers=auth_headers,
    )
    assert put.status_code == 200
    try:
        resp = await client.post(
            "/api/system/notifications/test",
            json={
                "type": "webhook",
                "name": "测试渠道",
                "config": {"url": "http://127.0.0.1:1/"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False  # 死端口：连接被拒绝
        assert body["error"]
    finally:
        # 恢复无渠道配置（即使断言失败也要执行）
        restore = await client.put(
            "/api/system/settings/notifications",
            json={"enabled": True, "channels": []},
            headers=auth_headers,
        )
        assert restore.status_code == 200


async def test_notification_test_unknown_type(client, auth_headers):
    resp = await client.post(
        "/api/system/notifications/test",
        json={"type": "xyz", "name": "未知类型"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "未知渠道类型" in body["error"]


async def test_notification_settings_rejects_bad_channels(client, auth_headers):
    bad_type = await client.put(
        "/api/system/settings/notifications",
        json={
            "enabled": True,
            "channels": [{"type": "xyz", "name": "未知类型渠道"}],
        },
        headers=auth_headers,
    )
    assert bad_type.status_code == 422
    assert bad_type.json()["detail"] == "未知通知渠道类型: xyz"

    missing_name = await client.put(
        "/api/system/settings/notifications",
        json={
            "enabled": True,
            "channels": [{"type": "webhook", "name": "   "}],
        },
        headers=auth_headers,
    )
    assert missing_name.status_code == 422
    assert missing_name.json()["detail"] == "通知渠道名称不能为空"


async def test_password_change_roundtrip(client, auth_headers):
    """改密 → 新密码可登录 → 改回默认密码（自恢复，且必须最后执行）。"""
    change = await client.put(
        "/api/auth/password",
        json={"old_password": "admin123", "new_password": "newpass123"},
        headers=auth_headers,
    )
    assert change.status_code == 200
    assert change.json() == {"ok": True}

    relogin = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "newpass123"}
    )
    assert relogin.status_code == 200

    wrong_old = await client.put(
        "/api/auth/password",
        json={"old_password": "wrong-old", "new_password": "another123"},
        headers=auth_headers,
    )
    assert wrong_old.status_code == 400
    assert wrong_old.json()["detail"] == "原密码错误"

    revert = await client.put(
        "/api/auth/password",
        json={"old_password": "newpass123", "new_password": "admin123"},
        headers=auth_headers,
    )
    assert revert.status_code == 200

    final = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert final.status_code == 200
