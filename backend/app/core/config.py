"""Application configuration for DailyKeeper.

Values come from ``DAILYKEEPER_*`` environment variables and an optional
``.env`` file; sensible dev defaults are provided for everything.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings, overridable via environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DAILYKEEPER_",
        env_file=".env",
        extra="ignore",
    )

    # Application
    app_name: str = "DailyKeeper"
    version: str = "0.1.0"
    env: str = "dev"
    log_level: str = "INFO"

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/dailykeeper.db"
    data_dir: str = "./data"

    # Security: encryption_key 为空时回退使用 secret_key
    secret_key: str = "dailykeeper-prod-default-secret-change-me"
    encryption_key: str = ""
    admin_username: str = "admin"
    admin_password: str = "admin123"
    access_token_expire_minutes: int = 1440

    # Scheduling
    timezone: str = "Asia/Shanghai"
    scheduler_interval_seconds: int = 30

    # Task worker
    worker_poll_seconds: int = 3
    worker_concurrency: int = 4
    task_timeout_seconds: int = 300
    http_timeout: int = 30
    max_retries: int = 3
    retry_backoff_seconds: int = 60

    # HTTP server
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
