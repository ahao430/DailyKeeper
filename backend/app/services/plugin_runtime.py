"""Plugin runtime: load plugins, build TaskContext and execute single task runs."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dailykeeper_sdk import HttpClient, TaskContext, TaskResult
from dailykeeper_sdk.registry import plugin_registry

from app.core.config import Settings
from app.core.security import CredentialCipher
from app.models import Account, Credential, Platform, TaskExecution
from app.services.task_engine import finalize_execution

logger = logging.getLogger(__name__)


async def load_plugins(session: AsyncSession) -> list[str]:
    """Load plugins via entry points and sync their manifests into ``platforms``.

    Idempotent: the registry warns on duplicate registrations, and existing
    ``Platform`` rows get their metadata refreshed while the ``enabled`` value
    chosen by the admin is preserved. Commits the session.
    """
    plugin_registry.load_entry_points()

    loaded_ids: list[str] = []
    for plugin_id, plugin_class in plugin_registry.all().items():
        manifest = plugin_class.manifest()
        metadata = {
            "name": manifest["plugin_name"],
            "version": manifest["version"],
            "description": manifest["description"],
            "auth_types": list(manifest["auth_types"]),
            "config_schema": list(manifest["config_schema"]),
            "account_schema": list(manifest["account_schema"]),
            "task_definitions": list(manifest["task_definitions"]),
            "source": "entry_point",
        }
        platform = await session.get(Platform, plugin_id)
        if platform is None:
            session.add(Platform(id=plugin_id, enabled=True, **metadata))
        else:
            for field, value in metadata.items():
                setattr(platform, field, value)
        loaded_ids.append(plugin_id)

    await session.commit()
    logger.info("插件加载完成，共 %s 个: %s", len(loaded_ids), ", ".join(sorted(loaded_ids)))
    return sorted(loaded_ids)


async def build_context(
    session: AsyncSession,
    execution: TaskExecution,
    cipher: CredentialCipher,
    settings: Settings,
) -> TaskContext:
    """Assemble the TaskContext for one execution (credentials, config, http, logger)."""
    account = await session.get(Account, execution.account_id)
    if account is None:
        raise ValueError(f"账号不存在: {execution.account_id}")
    instance = account.instance

    credential = await session.scalar(select(Credential).where(Credential.account_id == account.id))
    credentials = cipher.decrypt_dict(credential.data_encrypted) if credential is not None else {}

    # Account.config 为可选扩展列；当前模型未包含时视为空配置
    account_config = getattr(account, "config", None) or {}
    config = {**(instance.config or {}), **account_config}

    adapter = logging.LoggerAdapter(
        logging.getLogger("dailykeeper.task"),
        {
            "execution_id": execution.id,
            "account_id": execution.account_id,
            "task": execution.task_name,
        },
    )
    http = HttpClient(base_url=instance.base_url, timeout=settings.http_timeout)

    return TaskContext(
        execution_id=execution.id,
        account_id=execution.account_id,
        platform_id=instance.platform_id,
        platform_instance_id=instance.id,
        task_name=execution.task_name,
        credentials=credentials,
        config=config,
        base_url=instance.base_url,
        http=http,
        logger=adapter,
    )


def _scrub_secrets(message: str, secrets: list[str]) -> str:
    """Replace each credential value (length >= 8) occurring in the message with ``***``."""
    for secret in secrets:
        if len(secret) >= 8 and secret in message:
            message = message.replace(secret, "***")
    return message


async def run_execution(
    execution_id: int,
    *,
    session_factory,
    cipher: CredentialCipher,
    settings: Settings,
) -> TaskExecution | None:
    """Run one claimed execution in a fresh session and finalize it.

    Returns the execution after finalization, or the unchanged/None execution
    when it is missing or not in RUNNING state (i.e. not claimed by us).
    """
    async with session_factory() as session:
        execution = await session.get(TaskExecution, execution_id)
        if execution is None or execution.status != "RUNNING":
            return execution

        account = await session.get(Account, execution.account_id)
        if account is None:
            result = TaskResult.failed(f"账号不存在: {execution.account_id}")
        else:
            instance = account.instance
            plugin = plugin_registry.get(instance.platform_id)
            if plugin is None:
                result = TaskResult.failed(f"平台插件未加载: {instance.platform_id}")
            else:
                task_def = next(
                    (t for t in plugin.task_definitions if t.name == execution.task_name), None
                )
                if task_def is None:
                    result = TaskResult.failed(f"未知任务: {execution.task_name}")
                elif task_def.requires_browser:
                    result = TaskResult.needs_action("该任务需要浏览器自动化，将在后续版本支持")
                else:
                    result = await _execute_plugin(
                        session, execution, plugin, cipher, settings
                    )

        await finalize_execution(session, execution, result)
        return execution


async def _execute_plugin(
    session: AsyncSession,
    execution: TaskExecution,
    plugin,
    cipher: CredentialCipher,
    settings: Settings,
) -> TaskResult:
    """Run the plugin task with a timeout, closing the HTTP client afterwards."""
    context: TaskContext | None = None
    secrets: list[str] = []
    try:
        context = await build_context(session, execution, cipher, settings)
        secrets = [str(v) for v in context.credentials.values() if isinstance(v, str)]
        async with asyncio.timeout(settings.task_timeout_seconds):
            return await plugin.execute(execution.task_name, context)
    except TimeoutError:
        return TaskResult.failed(
            f"任务超时（超过 {settings.task_timeout_seconds}s）", retryable=True
        )
    except Exception as exc:  # noqa: BLE001 - 插件异常统一转换为失败结果
        logger.exception("任务执行异常 execution_id=%s task=%s", execution.id, execution.task_name)
        return TaskResult.failed(_scrub_secrets(str(exc), secrets), retryable=False)
    finally:
        if context is not None and context.http is not None:
            await context.http.aclose()
