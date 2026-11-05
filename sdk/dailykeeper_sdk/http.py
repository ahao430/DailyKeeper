"""Async HTTP client helper for plugins.

The runtime creates a fresh client per task execution and closes it after the
task finishes, so plugins never manage client lifecycle themselves.
"""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = 30.0


class HttpClient:
    """Thin wrapper around httpx.AsyncClient with DailyKeeper defaults."""

    def __init__(self, base_url: str = "", *, headers=None, cookies=None, timeout: float = DEFAULT_TIMEOUT):
        self._client = httpx.AsyncClient(
            base_url=(base_url or "").rstrip("/"),
            headers=headers or {},
            cookies=cookies or {},
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            trust_env=False,
        )

    def set_default_headers(self, headers: dict) -> None:
        self._client.headers.update(headers or {})

    def set_cookies(self, cookie_string: str | None = None, cookies: dict | None = None) -> None:
        if cookie_string:
            self._client.cookies.update(self._parse_cookie_string(cookie_string))
        if cookies:
            self._client.cookies.update(cookies)

    @property
    def raw(self) -> httpx.AsyncClient:
        """Access the underlying httpx.AsyncClient when the wrapper is not enough."""
        return self._client

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute an HTTP request. If base_url is configured, path may be relative; otherwise path must be a full URL."""
        return await self._client.request(method, path, **kwargs)

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _parse_cookie_string(value: str) -> dict:
        result = {}
        for part in (value or "").split(";"):
            if "=" in part:
                name, _, cookie_value = part.strip().partition("=")
                result[name] = cookie_value
        return result
