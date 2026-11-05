"""Bark push channel (iOS)."""

from __future__ import annotations

import httpx

from app.notifications.base import NotificationChannel

DEFAULT_SERVER = "https://api.day.app"


class BarkChannel(NotificationChannel):
    """Push via a Bark server: ``POST {server}/push``."""

    async def send(self, title: str, body: str) -> None:
        server = str(self.config.get("server") or DEFAULT_SERVER).rstrip("/")
        device_key = str(self.config.get("device_key") or "").strip()
        if not device_key:
            raise ValueError("Bark device_key 未配置")

        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.post(
                f"{server}/push",
                json={
                    "device_key": device_key,
                    "title": title,
                    "body": body,
                    "group": "DailyKeeper",
                },
            )
        if not response.is_success:
            raise RuntimeError(f"Bark 推送失败: HTTP {response.status_code}")
