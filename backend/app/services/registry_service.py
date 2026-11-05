"""可信插件目录（Registry）服务：白名单目录 + 安装状态比对。

安全模型（plan.md §11.3）：插件是可执行代码，V1 只提供**可信白名单目录**——
目录数据来自随仓库分发的 ``resources/registry.json``，不下载、不自动安装、
不执行任何第三方代码；安装/升级由管理员在服务器环境手动执行安装命令。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Platform

logger = logging.getLogger(__name__)

# app/services/registry_service.py → app/resources/registry.json
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "resources" / "registry.json"


def load_catalog() -> list[dict]:
    """Read the trusted catalog file; malformed or missing data yields ``[]``."""
    try:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("插件目录文件缺失: %s", _CATALOG_PATH)
        return []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("插件目录文件读取失败（%s）: %s", _CATALOG_PATH, exc)
        return []

    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        logger.warning("插件目录文件格式异常（缺少 plugins 列表），忽略")
        return []
    return [entry for entry in plugins if isinstance(entry, dict)]


def _version_key(version: str) -> tuple[int, ...]:
    """Parse ``"0.2.0"`` into ``(0, 2, 0)`` for segment-wise comparison.

    Non-numeric segments are tolerated and compared as ``0``; ``None``/empty
    versions degrade to ``(0,)`` so a missing value never reports upgradable.
    """
    parts: list[int] = []
    for segment in str(version or "").split("."):
        try:
            parts.append(int(segment.strip()))
        except ValueError:
            parts.append(0)
    return tuple(parts)


async def registry_catalog(session: AsyncSession) -> list[dict]:
    """Merge the trusted catalog with installed ``Platform`` rows.

    Each item is the catalog entry plus ``installed`` / ``installed_version`` /
    ``upgradable`` (catalog version newer than the installed one). Read-only:
    the caller's session is not committed.
    """
    result = await session.execute(select(Platform.id, Platform.version))
    installed = {row[0]: row[1] for row in result}

    items: list[dict] = []
    for entry in load_catalog():
        installed_version = installed.get(str(entry.get("plugin_id") or ""))
        upgradable = installed_version is not None and _version_key(
            str(entry.get("version") or "")
        ) > _version_key(installed_version)
        items.append(
            {
                **entry,
                "installed": installed_version is not None,
                "installed_version": installed_version,
                "upgradable": upgradable,
            }
        )
    return items
