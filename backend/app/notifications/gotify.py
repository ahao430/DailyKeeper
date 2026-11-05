"""Gotify push channel."""

from __future__ import annotations

import httpx

from app.notifications.base import NotificationChannel


class GotifyChannel(NotificationChannel):
    """Push via a Gotify server: ``POST {server}/message?token=...``."""

    async def send(self, title: str, body: str) -> None:
        server = str(self.config.get("server") or "").strip().rstrip("/")
        token = str(self.config.get("token") or "").strip()
        if not server:
            raise ValueError("Gotify server 未配置")
        if not token:
            raise ValueError("Gotify token 未配置")

        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.post(
                f"{server}/message",
                params={"token": token},
                json={"title": title, "message": body, "priority": 5},
            )
        if not response.is_success:
            raise RuntimeError(f"Gotify 推送失败: HTTP {response.status_code}")
