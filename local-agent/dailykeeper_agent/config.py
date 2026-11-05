"""Agent 配置：环境变量解析与 CLI 覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_SERVER = "DK_AGENT_SERVER"
ENV_TOKEN = "DK_AGENT_TOKEN"
ENV_POLL_SECONDS = "DK_AGENT_POLL_SECONDS"
ENV_HEARTBEAT_SECONDS = "DK_AGENT_HEARTBEAT_SECONDS"
ENV_TASK_CONCURRENCY = "DK_AGENT_TASK_CONCURRENCY"
ENV_VERIFY_TLS = "DK_AGENT_VERIFY_TLS"
ENV_TIMEOUT_SECONDS = "DK_AGENT_TIMEOUT_SECONDS"

_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass
class AgentConfig:
    """Agent 运行配置（心跳、轮询、并发与任务超时）。"""

    server_url: str
    token: str
    poll_seconds: float = 5.0
    heartbeat_seconds: float = 30.0
    task_concurrency: int = 2
    verify_tls: bool = True
    timeout_seconds: int = 300


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


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 不是合法整数: {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE_VALUES


def load_config(
    *, server_url: str | None = None, token: str | None = None
) -> AgentConfig:
    """组装 Agent 配置。

    优先级：显式参数（CLI 传入）> 环境变量 ``DK_AGENT_*`` > 默认值。
    ``server_url``/``token`` 缺失时抛出 :class:`ValueError`，中文报错列出
    所需环境变量，便于上层直接转为退出码。
    """
    resolved_server = server_url or _env_str(ENV_SERVER)
    resolved_token = token or _env_str(ENV_TOKEN)
    missing = [
        name
        for name, value in ((ENV_SERVER, resolved_server), (ENV_TOKEN, resolved_token))
        if not value
    ]
    if missing:
        raise ValueError(
            "缺少 DK_AGENT_SERVER 或 DK_AGENT_TOKEN 环境变量"
            f"（未设置: {', '.join(missing)}）；"
            "请导出环境变量或通过 --server/--token 参数指定"
        )

    return AgentConfig(
        server_url=(resolved_server or "").rstrip("/"),
        token=resolved_token or "",
        poll_seconds=_env_float(ENV_POLL_SECONDS, 5.0),
        heartbeat_seconds=_env_float(ENV_HEARTBEAT_SECONDS, 30.0),
        task_concurrency=_env_int(ENV_TASK_CONCURRENCY, 2),
        verify_tls=_env_bool(ENV_VERIFY_TLS, True),
        timeout_seconds=_env_int(ENV_TIMEOUT_SECONDS, 300),
    )
