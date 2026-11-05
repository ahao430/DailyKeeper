"""Registry 可信插件目录：API 集成测试 + 合并逻辑单元测试（全部只读，不留状态）。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from app.services import registry_service

_REPO_ROOT = Path(__file__).resolve().parents[2]

# requires_browser 按插件源码 task_definitions 实测：demo 有 browser_probe、
# mteam 有浏览器保活签到 → True；newapi / nexusphp 均为纯接口任务 → False。
_EXPECTED_REQUIRES_BROWSER = {"demo": True, "newapi": False, "mteam": True, "nexusphp": False}


def _pyproject_version(plugin_id: str) -> str:
    """读取 plugins/<id>/pyproject.toml 中的真实版本号（作为目录数据的基准）。"""
    path = _REPO_ROOT / "plugins" / plugin_id / "pyproject.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


async def test_registry_lists_official_plugins(client, auth_headers):
    """GET /api/registry 返回官方插件目录，安装状态与本地 platforms 表一致。"""
    resp = await client.get("/api/registry", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    items = resp.json()
    by_id = {item["plugin_id"]: item for item in items}
    assert {"demo", "newapi", "mteam", "nexusphp"} <= set(by_id)

    for plugin_id in ("demo", "newapi", "mteam", "nexusphp"):
        item = by_id[plugin_id]
        assert item["trusted"] is True
        assert item["author"] == "DailyKeeper Official"
        assert item["install"].startswith("pip install -e plugins/")
        assert item["capabilities"], "目录条目应携带任务能力清单"
        assert item["installed"] is True
        assert item["installed_version"] == _pyproject_version(plugin_id)
        assert item["upgradable"] is False
        assert item["requires_browser"] is _EXPECTED_REQUIRES_BROWSER[plugin_id]


async def test_registry_merge_logic(session_factory, monkeypatch):
    """版本逐段比较 + 目录与 platforms 表合并（未安装 / 已安装 / 可升级）。"""
    # _version_key：逐段元组比较，"0.10.0" > "0.9.0"；非数字段容错为 0
    assert registry_service._version_key("0.2.0") == (0, 2, 0)
    assert registry_service._version_key("0.10.0") > registry_service._version_key("0.9.0")
    assert registry_service._version_key("abc") == (0,)

    # 假条目（未安装的 plugin_id）→ installed=False，upgradable=False
    monkeypatch.setattr(
        registry_service,
        "load_catalog",
        lambda: [{"plugin_id": "fake", "version": "9.9.9"}],
    )
    async with session_factory() as session:
        catalog = await registry_service.registry_catalog(session)
    assert len(catalog) == 1
    assert catalog[0]["installed"] is False
    assert catalog[0]["installed_version"] is None
    assert catalog[0]["upgradable"] is False

    # 假条目伪装成已安装的 demo（目录版本 9.9.9 > 本地 0.1.0）→ installed + upgradable
    monkeypatch.setattr(
        registry_service,
        "load_catalog",
        lambda: [{"plugin_id": "demo", "version": "9.9.9"}],
    )
    async with session_factory() as session:
        catalog = await registry_service.registry_catalog(session)
    assert len(catalog) == 1
    assert catalog[0]["installed"] is True
    assert catalog[0]["installed_version"] == _pyproject_version("demo")
    assert catalog[0]["upgradable"] is True
