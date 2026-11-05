"""TaskContext passed to plugin execute()."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from dailykeeper_sdk.browser import BrowserSession
from dailykeeper_sdk.http import HttpClient


@dataclass
class TaskContext:
    """Runtime context handed to PlatformPlugin.execute() by the engine.

    The engine fills in credentials/config/http/logger per task execution;
    plugins only read from it. For tasks declared with ``requires_browser``,
    the browser worker additionally provides a Playwright-backed
    ``browser`` session (None everywhere else).
    """

    execution_id: int
    account_id: int
    platform_id: str
    platform_instance_id: int
    task_name: str
    credentials: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    base_url: str = ""
    http: HttpClient | None = None
    browser: BrowserSession | None = None
    logger: logging.LoggerAdapter | None = None
