"""ntfy push channel (ntfy.sh or self-hosted ntfy)."""

from __future__ import annotations

import httpx

from app.notifications.base import NotificationChannel

DEFAULT_SERVER = "https://ntfy.sh"


class NtfyChannel(NotificationChannel):
    """Push via ntfy JSON publish API: ``POST {server}/`` with {"topic": ...}.

    Works with the public ntfy.sh service and any self-hosted ntfy server.
    """

    async def send(self, title: str, body: str) -> None:
        server = str(self.config.get("server") or DEFAULT_SERVER).strip().rstrip("/")
        topic = str(self.config.get("topic") or "").strip()
        token = str(self.config.get("token") or "").strip()
        if not topic:
            raise ValueError("ntfy topic 未配置")

        headers = {}
        if token:
            # 受保护主题（访问控制开启）需要 Bearer token；公开主题无需填写
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.post(
                server,
                json={
                    "topic": topic,
                    "title": title,
                    "message": body,
                    "tags": ["sparkles"],
                },
                headers=headers,
            )
        if not response.is_success:
            raise RuntimeError(f"ntfy 推送失败: HTTP {response.status_code}")
