"""MCP Server 配置：环境变量解析与校验。

支持两种认证方式（二选一）：
- 静态令牌：``DK_MCP_TOKEN``（在服务器生成/下发的访问令牌）；
- 用户名密码：``DK_MCP_USERNAME`` + ``DK_MCP_PASSWORD``（首次调用时自动登录换取令牌）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_SERVER_URL = "DK_MCP_SERVER_URL"
ENV_TOKEN = "DK_MCP_TOKEN"
ENV_USERNAME = "DK_MCP_USERNAME"
ENV_PASSWORD = "DK_MCP_PASSWORD"
ENV_TIMEOUT = "DK_MCP_TIMEOUT_SECONDS"


@dataclass
class McpConfig:
    """MCP Server 连接 DailyKeeper 后端所需的配置。"""

    server_url: str = "http://127.0.0.1:8000"
    username: str = ""
    password: str = ""
    token: str = ""
    request_timeout: float = 60.0


def _env_str(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是合法数字: {raw!r}") from exc


def load_config() -> McpConfig:
    """从 ``DK_MCP_*`` 环境变量组装配置。

    校验规则：必须提供 ``DK_MCP_TOKEN``，或同时提供 ``DK_MCP_USERNAME`` 与
    ``DK_MCP_PASSWORD``；两者都缺失时抛出 :class:`ValueError`（中文报错），
    便于 MCP 客户端日志中直接定位。``server_url`` 去掉尾部 ``/``。
    """
    token = _env_str(ENV_TOKEN) or ""
    username = _env_str(ENV_USERNAME) or ""
    password = _env_str(ENV_PASSWORD) or ""
    if not token and not (username and password):
        raise ValueError(
            f"缺少 {ENV_TOKEN} 或 {ENV_USERNAME}/{ENV_PASSWORD} 环境变量；"
            "请在 MCP 客户端配置中提供静态令牌或用户名密码"
        )
    return McpConfig(
        server_url=(_env_str(ENV_SERVER_URL) or McpConfig.server_url).rstrip("/"),
        username=username,
        password=password,
        token=token,
        request_timeout=_env_float(ENV_TIMEOUT, 60.0),
    )
