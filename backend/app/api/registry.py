"""可信插件目录（Registry）API：只读目录 + 安装状态比对，不提供安装操作。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.services.registry_service import registry_catalog

router = APIRouter(
    prefix="/api/registry", tags=["registry"], dependencies=[Depends(get_current_admin)]
)


@router.get("")
async def list_registry(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """可信白名单目录，每项附带本地安装状态（installed / installed_version / upgradable）。"""
    return await registry_catalog(session)
