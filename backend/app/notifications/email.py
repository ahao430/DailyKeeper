"""Email (SMTP) notification channel."""

from __future__ import annotations

import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from app.notifications.base import NotificationChannel


class EmailChannel(NotificationChannel):
    """Send via SMTP. SSL (port 465) or STARTTLS (port 587, default when
    username is set). Blocking smtplib calls run in a worker thread so the
    event loop is never blocked."""

    async def send(self, title: str, body: str) -> None:
        host = str(self.config.get("host") or "").strip()
        to_addr = str(self.config.get("to") or "").strip()
        if not host:
            raise ValueError("SMTP 服务器未配置")
        if not to_addr:
            raise ValueError("收件邮箱未配置")

        from_addr = str(self.config.get("from") or "").strip() or to_addr
        username = str(self.config.get("username") or "").strip()
        password = str(self.config.get("password") or "")
        use_ssl = bool(self.config.get("use_ssl", True))
        try:
            port = int(self.config.get("port") or (465 if use_ssl else 587))
        except (TypeError, ValueError):
            raise ValueError("SMTP 端口必须是数字") from None

        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = Header(title, "utf-8")
        message["From"] = formataddr((str(Header("DailyKeeper", "utf-8")), from_addr))
        message["To"] = to_addr

        await asyncio.to_thread(
            self._send_mail,
            host,
            port,
            use_ssl,
            username,
            password,
            from_addr,
            to_addr,
            message.as_string(),
        )

    @staticmethod
    def _send_mail(
        host: str,
        port: int,
        use_ssl: bool,
        username: str,
        password: str,
        from_addr: str,
        to_addr: str,
        payload: str,
    ) -> None:
        if use_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            client = smtplib.SMTP(host, port, timeout=15)
        try:
            if not use_ssl and username:
                client.starttls()
            if username:
                client.login(username, password)
            client.sendmail(from_addr, [to_addr], payload)
        except smtplib.SMTPException as exc:
            raise RuntimeError(f"邮件发送失败: {exc}") from exc
        finally:
            try:
                client.quit()
            except Exception:  # noqa: BLE001 - 退出失败无需上报
                pass
