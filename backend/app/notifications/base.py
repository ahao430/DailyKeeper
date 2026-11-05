"""Notification channel base class."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """Base class for notification channels.

    Subclasses read their settings from the ``config`` dict passed in and
    implement :meth:`send`, raising an exception on delivery failure.
    """

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    @abstractmethod
    async def send(self, title: str, body: str) -> None:
        """Send one notification. Raise on failure."""
