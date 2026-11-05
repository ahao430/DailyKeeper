"""Agent 主循环：心跳 → 认领 → 执行 → 回传，循环往复。

服务器不可达时仅告警并退避重试（离线容忍），绝不退出进程；单个任务的
任何异常都被捕获并记录，不影响主循环。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import httpx

from dailykeeper_sdk.registry import plugin_registry

from dailykeeper_agent import __version__
from dailykeeper_agent.client import AgentClient
from dailykeeper_agent.config import AgentConfig, load_config
from dailykeeper_agent.runner import AgentRunner

logger = logging.getLogger("dailykeeper.agent")

CLAIM_BATCH_LIMIT = 5  # 服务器单次认领上限
RECONNECT_BACKOFF_SECONDS = 5.0  # 服务器不可达时的退避间隔


async def _process_one(
    client: AgentClient, runner: AgentRunner, semaphore: asyncio.Semaphore, task: dict
) -> None:
    """处理单个认领到的任务：取上下文 → 本地执行 → 回传结果。"""
    async with semaphore:
        execution_id = task.get("id")
        try:
            context_payload = await client.task_context(execution_id)
            payload = await runner.execute(context_payload)
            reply = await client.post_result(execution_id, payload)
            final_status = reply.get("final_status") or payload.get("status")
            if payload.get("success"):
                logger.info(
                    "任务 #%s (%s/%s) 完成: %s",
                    execution_id, task.get("platform_id"), task.get("task_name"), final_status,
                )
            else:
                logger.warning(
                    "任务 #%s (%s/%s) 未成功: %s %s",
                    execution_id, task.get("platform_id"), task.get("task_name"),
                    final_status, payload.get("message"),
                )
        except Exception:  # noqa: BLE001 - 单任务失败绝不能击穿主循环
            logger.exception("处理任务 #%s 失败", execution_id)


async def run(config: AgentConfig) -> None:
    """Agent 守护主循环（永不正常返回，靠 KeyboardInterrupt 退出）。"""
    client = AgentClient(config)
    runner = AgentRunner(config)
    semaphore = asyncio.Semaphore(max(1, config.task_concurrency))
    last_heartbeat = float("-inf")  # 首轮立即心跳
    logger.info(
        "DailyKeeper Agent v%s 启动（server=%s, 并发=%s, 已加载插件=%s）",
        __version__,
        config.server_url,
        config.task_concurrency,
        ", ".join(sorted(plugin_ids())) or "无",
    )

    try:
        while True:
            try:
                if time.monotonic() - last_heartbeat >= config.heartbeat_seconds:
                    reply = await client.heartbeat(
                        version=__version__, capabilities=["http"]  # 浏览器能力后续提供
                    )
                    interval = reply.get("heartbeat_interval_seconds")
                    if isinstance(interval, (int, float)) and interval > 0:
                        config.heartbeat_seconds = float(interval)
                    last_heartbeat = time.monotonic()
                    logger.debug("心跳成功: %s", reply)

                tasks = await client.claim_tasks(limit=CLAIM_BATCH_LIMIT)
                if not tasks:
                    await asyncio.sleep(config.poll_seconds)
                    continue

                await asyncio.gather(
                    *(_process_one(client, runner, semaphore, task) for task in tasks)
                )
            except (httpx.HTTPError, RuntimeError) as exc:
                # 服务器暂时不可达/令牌失效：容忍并退避重试，保持离线韧性。
                logger.warning("与服务器通信失败，%.0f 秒后重试: %s", RECONNECT_BACKOFF_SECONDS, exc)
                await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)
    finally:
        await client.aclose()
        logger.info("DailyKeeper Agent 已停止")


def plugin_ids() -> list[str]:
    """当前本地环境中已注册的插件 id 列表（供启动横幅/CLI 使用）。"""
    return sorted(plugin_registry.all().keys())


def main_sync(config: AgentConfig | None = None) -> None:
    """控制台入口：读配置并启动主循环，Ctrl+C 优雅退出。"""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    if config is None:
        try:
            config = load_config()
        except ValueError as exc:
            print(f"配置错误: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        print("\n收到中断信号，DailyKeeper Agent 已退出")


if __name__ == "__main__":
    main_sync()
