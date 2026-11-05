"""Generic webhook channel."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.notifications.base import NotificationChannel


class WebhookChannel(NotificationChannel):
    """POST a JSON payload to a user-provided URL."""

    async def send(self, title: str, body: str) -> None:
        url = str(self.config.get("url") or "").strip()
        if not url:
            raise ValueError("Webhook url 未配置")

        payload = {
            "title": title,
            "body": body,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.post(url, json=payload)
        if not response.is_success:
            raise RuntimeError(f"Webhook 推送失败: HTTP {response.status_code}")
