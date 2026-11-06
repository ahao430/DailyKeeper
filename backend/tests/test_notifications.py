"""Notification channel unit tests: ntfy and email channels."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.notifications import CHANNEL_TYPES, EmailChannel, NtfyChannel


def test_channel_registry_contains_new_channels() -> None:
    assert CHANNEL_TYPES["ntfy"] is NtfyChannel
    assert CHANNEL_TYPES["email"] is EmailChannel


@pytest.mark.asyncio
async def test_ntfy_channel_posts_json_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    """ntfy 走 JSON 发布 API：POST {server}/，body 含 topic/title/message。"""
    calls: list[SimpleNamespace] = []

    class FakeResponse:
        is_success = True
        status_code = 200

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, json: dict | None = None, headers: dict | None = None) -> FakeResponse:
            calls.append(SimpleNamespace(url=url, json=json, headers=headers))
            return FakeResponse()

    monkeypatch.setattr("app.notifications.ntfy.httpx.AsyncClient", FakeClient)

    channel = NtfyChannel({"topic": "dk-test", "token": "tok123"})
    await channel.send("签到成功", "M-Team 已保活")

    assert len(calls) == 1
    assert calls[0].url == "https://ntfy.sh"
    assert calls[0].json == {
        "topic": "dk-test",
        "title": "签到成功",
        "message": "M-Team 已保活",
        "tags": ["sparkles"],
    }
    assert calls[0].headers == {"Authorization": "Bearer tok123"}


@pytest.mark.asyncio
async def test_ntfy_channel_requires_topic() -> None:
    channel = NtfyChannel({})
    with pytest.raises(ValueError, match="topic"):
        await channel.send("t", "b")


@pytest.mark.asyncio
async def test_email_channel_sends_over_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSL 模式：SMTP_SSL(host, 465)，login 后 sendmail。"""
    sent: list[SimpleNamespace] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 15) -> None:
            sent.append(SimpleNamespace(kind="init", host=host, port=port))
            self.mail_options: list[str] = []

        def login(self, user: str, password: str) -> None:
            sent.append(SimpleNamespace(kind="login", user=user, password=password))

        def sendmail(self, from_addr: str, to_addrs: list[str], payload: str) -> None:
            sent.append(SimpleNamespace(kind="send", frm=from_addr, to=to_addrs, payload=payload))

        def quit(self) -> None:
            sent.append(SimpleNamespace(kind="quit", args=None))

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP_SSL", FakeSMTP)

    channel = EmailChannel(
        {
            "host": "smtp.example.com",
            "port": 465,
            "use_ssl": True,
            "username": "bot@example.com",
            "password": "secret",
            "from": "noreply@example.com",
            "to": "me@example.com",
        }
    )
    await channel.send("任务失败", "newapi 签到失败")

    kinds = [item.kind for item in sent]
    assert kinds == ["init", "login", "send", "quit"]
    assert sent[0].host == "smtp.example.com" and sent[0].port == 465
    assert sent[2].frm == "noreply@example.com" and sent[2].to == ["me@example.com"]
    # 邮件正文与主题在 MIME 载荷里（utf-8 编码）
    assert "任务失败" in sent[2].payload or "Subject" in sent[2].payload


@pytest.mark.asyncio
async def test_email_channel_requires_host_and_to() -> None:
    with pytest.raises(ValueError, match="SMTP"):
        await EmailChannel({"to": "me@example.com"}).send("t", "b")
    with pytest.raises(ValueError, match="收件"):
        await EmailChannel({"host": "smtp.example.com"}).send("t", "b")


@pytest.mark.asyncio
async def test_email_channel_wraps_smtp_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import smtplib

    class BrokenSMTP:
        def __init__(self, host: str, port: int, timeout: int = 15) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        def quit(self) -> None:
            pass

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP_SSL", BrokenSMTP)

    channel = EmailChannel({"host": "smtp.example.com", "to": "me@example.com", "username": "u", "password": "p"})
    with pytest.raises(RuntimeError, match="邮件发送失败"):
        await channel.send("t", "b")
