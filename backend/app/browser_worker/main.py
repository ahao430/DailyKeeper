"""Browser worker daemon: executes needs_browser tasks with Playwright.

One Chromium instance lives for the whole worker lifetime; each execution gets
a fresh browser context (restored from the account's persisted storage state
when available) that is closed — and its state persisted — after the run.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Browser, BrowserContext

from app.core.config import Settings, get_settings
from app.core.database import ensure_schema, get_session_factory, init_engine
from app.core.security import get_cipher
from app.services.plugin_runtime import load_plugins, run_execution
from app.services.task_engine import claim_pending, recover_interrupted

logger = logging.getLogger(__name__)


def browser_state_path(settings: Settings, account_id: int) -> str:
    """Return the per-account storage-state file path (creating the directory)."""
    state_dir = Path(settings.browser_state_dir or Path(settings.data_dir) / "browser_states")
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / f"account-{account_id}.json")


async def persist_browser_state(
    browser_context: BrowserContext, settings: Settings, account_id: int
) -> None:
    """Persist cookies/localStorage of a still-open context to the state file.

    Called by the browser worker after ``run_execution`` returns — success or
    failure alike, since login state may have been written mid-flow — and
    always BEFORE the context is closed.
    """
    try:
        await browser_context.storage_state(path=browser_state_path(settings, account_id))
    except Exception:  # noqa: BLE001 - 状态持久化失败不阻断任务收尾
        logger.warning("保存浏览器登录状态失败 account_id=%s", account_id, exc_info=True)


async def _run_one(
    execution_id: int,
    account_id: int,
    locks: dict[int, asyncio.Lock],
    session_factory,
    cipher,
    settings: Settings,
    playwright_browser: Browser,
) -> None:
    """Run one needs_browser execution in a fresh Playwright context.

    Holds the account lock for the whole run; restores the account's saved
    storage state when present, then persists whatever state the run left and
    closes the context (the shared browser itself stays open).
    """
    async with locks[account_id]:
        state_path = browser_state_path(settings, account_id)
        state_kwargs = {"storage_state": state_path} if Path(state_path).exists() else {}
        browser_ctx = await playwright_browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="zh-CN", **state_kwargs
        )
        try:
            page = await browser_ctx.new_page()
            try:
                await run_execution(
                    execution_id,
                    session_factory=session_factory,
                    cipher=cipher,
                    settings=settings,
                    browser_page=page,
                    browser_context=browser_ctx,
                )
            finally:
                await persist_browser_state(browser_ctx, settings, account_id)
        finally:
            await browser_ctx.close()


async def main() -> None:
    from playwright.async_api import async_playwright

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    init_engine(settings)
    session_factory = get_session_factory()

    await ensure_schema()  # 与 API 进程并行启动时避免建表竞态
    async with session_factory() as session:
        await load_plugins(session)
        await recover_interrupted(session, browser=True)  # 仅恢复浏览器任务，避免误伤 HTTP Worker

    cipher = get_cipher(settings)
    worker_id = f"browser-{uuid4().hex[:8]}"
    locks: dict[int, asyncio.Lock] = {}
    logger.info(
        "DailyKeeper Browser Worker started (%s, concurrency=%s, headless=%s)",
        worker_id,
        settings.browser_worker_concurrency,
        settings.browser_headless,
    )

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=settings.browser_headless,
                slow_mo=settings.browser_slow_mo_ms or None,
            )
            try:
                while True:
                    async with session_factory() as session:
                        executions = await claim_pending(
                            session,
                            worker_id,
                            limit=settings.browser_worker_concurrency,
                            browser=True,
                        )
                        await session.commit()

                    if not executions:
                        await asyncio.sleep(settings.worker_poll_seconds)
                        continue

                    for execution in executions:
                        locks.setdefault(execution.account_id, asyncio.Lock())
                    tasks = [
                        asyncio.create_task(
                            _run_one(
                                execution.id,
                                execution.account_id,
                                locks,
                                session_factory,
                                cipher,
                                settings,
                                browser,
                            )
                        )
                        for execution in executions
                    ]
                    await asyncio.gather(*tasks)
            finally:
                await browser.close()
    except KeyboardInterrupt:
        logger.info("Browser Worker 收到中断信号，已退出")


if __name__ == "__main__":
    asyncio.run(main())
