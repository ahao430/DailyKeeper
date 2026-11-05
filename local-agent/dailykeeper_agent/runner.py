"""本地任务执行器：加载本机插件并执行服务器下发的任务。"""

from __future__ import annotations

import asyncio
import logging

from dailykeeper_sdk import HttpClient, TaskContext, TaskDefinition
from dailykeeper_sdk.registry import plugin_registry

from dailykeeper_agent.config import AgentConfig

logger = logging.getLogger("dailykeeper.agent")


def _collect_secrets(value: object, secrets: list[str]) -> None:
    """递归收集凭据树中长度 ≥8 的字符串值（可能出现在日志/异常里的敏感信息）。"""
    if isinstance(value, str):
        if len(value) >= 8:
            secrets.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_secrets(item, secrets)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_secrets(item, secrets)


def scrub_message(message: str, credentials: dict) -> str:
    """把消息中出现的凭据字符串值替换为 ***（长秘钥优先，避免部分遮蔽）。"""
    secrets: list[str] = []
    _collect_secrets(credentials or {}, secrets)
    scrubbed = message or ""
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret in scrubbed:
            scrubbed = scrubbed.replace(secret, "***")
    return scrubbed


class AgentRunner:
    """在本地插件环境中执行服务器下发的任务，产出可回传的结果负载。"""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        # 插件来自 Agent 自身环境（pip install 的插件包），加载幂等可重复调用。
        plugin_registry.load_entry_points()

    def _failure(self, message: str, *, data: dict | None = None) -> dict:
        return {
            "success": False,
            "status": "FAILED",
            "message": message,
            "data": data or {},
            "metrics": {},
        }

    async def execute(self, context_payload: dict) -> dict:
        """按服务器下发的上下文执行一个任务，返回 post_result 负载。

        任何失败（插件缺失、任务不支持、超时、插件异常）都转为 FAILED
        结果负载而不是抛异常，由主循环回传服务器。
        """
        platform_id = str(context_payload.get("platform_id") or "")
        plugin = plugin_registry.get(platform_id)
        if plugin is None:
            return self._failure(f"本地未安装平台插件: {platform_id}")

        task_name = str(context_payload.get("task_name") or "")
        task_def: TaskDefinition | None = next(
            (t for t in plugin.task_definitions if t.name == task_name), None
        )
        if task_def is None:
            return self._failure(f"本地插件不支持任务: {task_name}")

        execution_id = int(context_payload.get("execution_id") or 0)
        credentials = context_payload.get("credentials") or {}
        config = context_payload.get("config") or {}
        base_url = str(context_payload.get("base_url") or "")
        try:
            http_timeout = int(context_payload.get("http_timeout") or 30)
        except (TypeError, ValueError):
            http_timeout = 30
        try:
            timeout_seconds = float(
                context_payload.get("timeout_seconds") or self._config.timeout_seconds
            )
        except (TypeError, ValueError):
            timeout_seconds = float(self._config.timeout_seconds)

        # 服务器内部账号/实例 ID 不下发，本地无意义，占位为 0。
        context = TaskContext(
            execution_id=execution_id,
            account_id=0,
            platform_id=platform_id,
            platform_instance_id=0,
            task_name=task_name,
            credentials=credentials,
            config=config,
            base_url=base_url,
            http=HttpClient(base_url=base_url, timeout=http_timeout),
            logger=logging.LoggerAdapter(
                logger, {"execution_id": execution_id, "platform_id": platform_id}
            ),
        )

        try:
            async with asyncio.timeout(timeout_seconds):
                result = await plugin.execute(task_name, context)
        except TimeoutError:
            # 重试策略由服务器侧决定，本地标记为不可重试失败。
            return self._failure("任务超时", data={"retryable": False})
        except Exception as exc:  # noqa: BLE001 - 插件任意异常都不能击穿执行循环
            logger.exception("任务 #%s (%s/%s) 执行异常", execution_id, platform_id, task_name)
            return self._failure(scrub_message(f"插件执行异常: {exc}", credentials))
        finally:
            await context.http.aclose()

        return {
            "success": result.success,
            "status": result.status.value,
            "message": result.message,
            "data": result.data,
            "metrics": result.metrics,
        }
