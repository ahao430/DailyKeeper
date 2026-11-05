"""多用户（多管理员）管理测试：创建/登录/停用/删除守卫/密码重置/种子迁移。

依赖 conftest 的会话级启动：首次启动自动播种 admin 账号（环境变量默认口令）。
用例按文件内顺序执行，前后用例共享已创建的用户（ops）。
"""

from __future__ import annotations

from httpx import AsyncClient

OP_USERNAME = "ops"
OP_PASSWORD = "opspass123"
OP_DISPLAY = "运维"


async def _login(client: AsyncClient, username: str, password: str):
    return await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


async def _list_users(client: AsyncClient, auth_headers: dict) -> list[dict]:
    resp = await client.get("/api/users", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _find_user(client: AsyncClient, auth_headers: dict, username: str) -> dict:
    users = await _list_users(client, auth_headers)
    return next(user for user in users if user["username"] == username)


async def _ensure_ops_user(client: AsyncClient, auth_headers: dict) -> dict:
    """创建 ops 用户（已存在则忽略 409），返回其详情。"""
    created = await client.post(
        "/api/users",
        json={
            "username": OP_USERNAME,
            "password": OP_PASSWORD,
            "display_name": OP_DISPLAY,
        },
        headers=auth_headers,
    )
    assert created.status_code in (200, 409), created.text
    return await _find_user(client, auth_headers, OP_USERNAME)


async def test_user_crud_and_login(client, auth_headers):
    ops = await _ensure_ops_user(client, auth_headers)
    assert ops["display_name"] == OP_DISPLAY
    assert ops["enabled"] is True
    assert ops["role"] == "admin"
    assert "password_hash" not in ops

    # 新用户可登录，/me 返回 display_name / role
    login = await _login(client, OP_USERNAME, OP_PASSWORD)
    assert login.status_code == 200, login.text
    ops_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/auth/me", headers=ops_headers)
    assert me.status_code == 200, me.text
    assert me.json() == {"username": OP_USERNAME, "display_name": OP_DISPLAY, "role": "admin"}

    # 重复用户名 → 409
    duplicate = await client.post(
        "/api/users",
        json={"username": OP_USERNAME, "password": "whatever123"},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "用户名已存在"

    # 停用 ops：登录 401，旧令牌立即失效
    disabled = await client.put(
        f"/api/users/{ops['id']}", json={"enabled": False}, headers=auth_headers
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    disabled_login = await _login(client, OP_USERNAME, OP_PASSWORD)
    assert disabled_login.status_code == 401
    assert disabled_login.json()["detail"] == "用户名或密码错误"

    stale = await client.get("/api/users", headers=ops_headers)
    assert stale.status_code == 401
    assert stale.json()["detail"] == "未登录或登录已过期"

    # 管理员重新启用后可再次登录
    reenabled = await client.put(
        f"/api/users/{ops['id']}", json={"enabled": True}, headers=auth_headers
    )
    assert reenabled.status_code == 200, reenabled.text
    ok_login = await _login(client, OP_USERNAME, OP_PASSWORD)
    assert ok_login.status_code == 200, ok_login.text


async def test_user_guards(client, auth_headers):
    me = await client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    admin = await _find_user(client, auth_headers, me.json()["username"])

    # 不能停用自己的账号
    disable_self = await client.put(
        f"/api/users/{admin['id']}", json={"enabled": False}, headers=auth_headers
    )
    assert disable_self.status_code == 400
    assert disable_self.json()["detail"] == "不能停用自己的账号"

    # 不能删除自己的账号
    delete_self = await client.delete(f"/api/users/{admin['id']}", headers=auth_headers)
    assert delete_self.status_code == 400
    assert delete_self.json()["detail"] == "不能删除自己的账号"

    # 注：删除最后一个用户的守卫（至少保留一个用户）无法在不触犯
    # 「不能删除自己」的情况下由管理端触达，故不单独覆盖。

    # 管理员重置 ops 密码：旧密码 401，新密码可登录
    ops = await _ensure_ops_user(client, auth_headers)
    reset = await client.put(
        f"/api/users/{ops['id']}/password",
        json={"new_password": "resetpass123"},
        headers=auth_headers,
    )
    assert reset.status_code == 200, reset.text
    assert reset.json() == {"ok": True}

    old_login = await _login(client, OP_USERNAME, OP_PASSWORD)
    assert old_login.status_code == 401
    new_login = await _login(client, OP_USERNAME, "resetpass123")
    assert new_login.status_code == 200, new_login.text

    # 删除用户后：该用户登录 401
    removed = await client.delete(f"/api/users/{ops['id']}", headers=auth_headers)
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"ok": True}
    after_delete = await _login(client, OP_USERNAME, "resetpass123")
    assert after_delete.status_code == 401


async def test_seed_admin_user(client, auth_headers):
    """启动种子：admin 已由 ensure_admin_user 播种且已启用，登录时间已记录。"""
    users = await _list_users(client, auth_headers)
    admin = next(user for user in users if user["username"] == "admin")
    assert admin["enabled"] is True
    assert admin["last_login_at"] is not None
    assert admin["created_at"] is not None
