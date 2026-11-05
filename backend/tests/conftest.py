"""pytest fixtures for DailyKeeper backend tests.

Environment variables are set BEFORE any ``app.*`` import so that the cached
Settings instance picks up the test database and secret key. The whole suite
shares one application, one SQLite database and one event loop (see the
session loop-scope options in the root ``pyproject.toml``).
"""

from __future__ import annotations

import os
import uuid

_TEST_TOKEN = uuid.uuid4().hex[:8]
_TEST_DB_PATH = f"/tmp/dk-test-{_TEST_TOKEN}.db"
os.environ["DAILYKEEPER_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ["DAILYKEEPER_SECRET_KEY"] = "test-secret-key-not-for-prod"
os.environ["DAILYKEEPER_DATA_DIR"] = f"/tmp/dk-test-data-{_TEST_TOKEN}"
os.environ["DAILYKEEPER_LOG_LEVEL"] = "WARNING"

import pytest
from httpx import ASGITransport, AsyncClient

from dailykeeper_sdk.registry import plugin_registry

from dailykeeper_plugin_demo.plugin import DemoPlugin

try:  # mteam 插件用于浏览器自动化守卫用例；缺失时跳过对应测试
    from dailykeeper_plugin_mteam.plugin import MTeamPlugin

    _MTEAM_AVAILABLE = True
except ImportError:  # pragma: no cover - 仅在插件未安装时触发
    MTeamPlugin = None  # type: ignore[assignment]
    _MTEAM_AVAILABLE = False

from app.core.database import dispose_engine, get_session_factory

# 共享演示实例的缓存 id（整个测试会话复用同一实例）
_demo_instance_id: int | None = None


@pytest.fixture(scope="session", autouse=True)
async def _app_setup():
    """Initialize the app once per test session and clean up afterwards."""
    plugin_registry.register(DemoPlugin)
    if _MTEAM_AVAILABLE:
        plugin_registry.register(MTeamPlugin)

    from app import main as app_main

    await app_main.run_startup()
    yield
    await dispose_engine()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(f"{_TEST_DB_PATH}{suffix}")
        except FileNotFoundError:
            pass


@pytest.fixture(scope="session")
async def client():
    """HTTP client bound to the real ASGI app (no lifespan, startup is manual)."""
    from app import main as app_main

    transport = ASGITransport(app=app_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(scope="session")
async def auth_headers(client):
    """Authorization headers for the default admin account."""
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def session_factory():
    return get_session_factory()


async def get_or_create_demo_instance(client, auth_headers) -> int:
    """Return the id of the shared demo platform instance (created once)."""
    global _demo_instance_id
    if _demo_instance_id is None:
        response = await client.post(
            "/api/platforms",
            json={
                "platform_id": "demo",
                "name": "演示实例",
                "base_url": "",
                "config": {},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        _demo_instance_id = response.json()["id"]
    return _demo_instance_id


async def create_demo_account(
    client,
    auth_headers,
    *,
    behavior: str = "success",
    balance: float = 0.0,
    points: float = 0.0,
) -> dict:
    """Create a fresh demo account with a unique name and return its API dict.

    Each test creates its own account, so tests stay independent — execution
    dedupe is keyed by (account, task, business_date).
    """
    instance_id = await get_or_create_demo_instance(client, auth_headers)
    response = await client.post(
        "/api/accounts",
        json={
            "instance_id": instance_id,
            "name": f"acct-{uuid.uuid4().hex[:10]}",
            "display_name": "测试账号",
            "config": {"behavior": behavior, "balance": balance, "points": points},
            "credential": {"kind": "token", "data": {"token": "test-token-1234567890"}},
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()
