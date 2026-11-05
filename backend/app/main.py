"""FastAPI application factory: ``uvicorn app.main:app`` from the backend directory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, agent_api, agents, auth, executions, platforms, registry, resources, system, tasks
from app.core.config import get_settings
from app.core.database import dispose_engine, get_session_factory, init_engine
from app.models.tables import Base
from app.services.plugin_runtime import load_plugins

logger = logging.getLogger(__name__)


async def run_startup() -> None:
    """Prepare storage and plugins; runs once on application startup."""
    settings = get_settings()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    init_engine(settings)

    session_factory = get_session_factory()
    async with session_factory() as session:
        conn = await session.connection()
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(bind=sync_conn))
        await session.commit()
        await load_plugins(session)  # 内部已 commit

    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logger.info("DailyKeeper 启动完成 (env=%s, version=%s)", settings.env, settings.version)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DailyKeeper Server", version=settings.version, lifespan=lifespan)

    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    app.include_router(auth.router)
    app.include_router(platforms.router)
    app.include_router(accounts.router)
    app.include_router(tasks.router)
    app.include_router(executions.router)
    app.include_router(resources.router)
    app.include_router(system.router)
    app.include_router(registry.router)
    app.include_router(agents.router)
    app.include_router(agent_api.router)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        return {"status": "ok", "version": settings.version}

    return app


app = create_app()
