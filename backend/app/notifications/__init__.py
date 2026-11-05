"""Notification channel implementations (Bark / Gotify / Webhook)."""

from app.notifications.base import NotificationChannel
from app.notifications.bark import BarkChannel
from app.notifications.gotify import GotifyChannel
from app.notifications.webhook import WebhookChannel

CHANNEL_TYPES: dict[str, type[NotificationChannel]] = {
    "bark": BarkChannel,
    "gotify": GotifyChannel,
    "webhook": WebhookChannel,
}

__all__ = [
    "BarkChannel",
    "CHANNEL_TYPES",
    "GotifyChannel",
    "NotificationChannel",
    "WebhookChannel",
]
