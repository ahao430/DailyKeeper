"""Browser session wrapper handed to plugins for browser-automation tasks.

The SDK does NOT depend on Playwright directly: the runtime (browser worker)
creates the real Playwright objects and passes them in, so plugins that never
declare ``requires_browser`` tasks do not need Playwright installed. All page
objects here are typed as ``Any`` deliberately.
"""

from __future__ import annotations

from typing import Any


class BrowserSession:
    """Thin convenience wrapper over a Playwright page + context.

    Plugins may use ``session.page`` / ``session.context`` directly (full
    Playwright API), or the small helpers below.
    """

    def __init__(self, page: Any, context: Any) -> None:
        self.page = page
        self.context = context

    @property
    def url(self) -> str:
        return self.page.url

    async def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> Any:
        """Navigate and return the response."""
        return await self.page.goto(url, wait_until=wait_until)

    async def click(self, selector: str, *, timeout_ms: int = 15000) -> None:
        await self.page.click(selector, timeout=timeout_ms)

    async def fill(self, selector: str, value: str, *, timeout_ms: int = 15000) -> None:
        await self.page.fill(selector, value, timeout=timeout_ms)

    async def text(self, selector: str | None = None) -> str:
        """Full page text, or the text content of one selector."""
        if selector is None:
            return await self.page.inner_text("body")
        return await self.page.inner_text(selector)

    async def wait_for_selector(self, selector: str, *, timeout_ms: int = 15000) -> Any:
        return await self.page.wait_for_selector(selector, timeout=timeout_ms)

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(path=path, full_page=True)

    async def close(self) -> None:
        await self.context.close()
