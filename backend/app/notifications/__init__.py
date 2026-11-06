"""Notification channel implementations (Bark / Gotify / Webhook / ntfy / Email)."""

from app.notifications.base import NotificationChannel
from app.notifications.bark import BarkChannel
from app.notifications.email import EmailChannel
from app.notifications.gotify import GotifyChannel
from app.notifications.ntfy import NtfyChannel
from app.notifications.webhook import WebhookChannel

CHANNEL_TYPES: dict[str, type[NotificationChannel]] = {
    "bark": BarkChannel,
    "gotify": GotifyChannel,
    "webhook": WebhookChannel,
    "ntfy": NtfyChannel,
    "email": EmailChannel,
}

__all__ = [
    "BarkChannel",
    "CHANNEL_TYPES",
    "EmailChannel",
    "GotifyChannel",
    "NotificationChannel",
    "NtfyChannel",
    "WebhookChannel",
]
