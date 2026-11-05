"""Platform plugins and platform instances (site deployments) management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dailykeeper_sdk.registry import plugin_registry

from app.api.deps import get_current_admin, get_db
from app.models import PlatformInstance

router = APIRouter(prefix="/api", tags=["platforms"], dependencies=[Depends(get_current_admin)])


class CreatePlatformRequest(BaseModel):
    platform_id: str
    name: str
    base_url: str = ""
    config: dict = {}
    timezone: str = "Asia/Shanghai"
    description: str = ""
    enabled: bool = True


class UpdatePlatformRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    config: dict | None = None
    timezone: str | None = None
    description: str | None = None
    enabled: bool | None = None


def _instance_detail(instance: PlatformInstance, platform_name: str) -> dict:
    """Serialize one platform instance (its relationships must be loaded)."""
    return {
        "id": instance.id,
        "platform_id": instance.platform_id,
        "platform_name": platform_name,
        "name": instance.name,
        "base_url": instance.base_url,
        "config": instance.config,
        "timezone": instance.timezone,
        "description": instance.description,
        "enabled": instance.enabled,
        "account_count": len(instance.accounts),
    }


@router.get("/plugins")
async def list_plugins() -> list[dict]:
    """Manifests of all loaded platform plugins."""
    return [{**plugin.manifest(), "enabled": True} for plugin in plugin_registry.all().values()]


@router.get("/platforms")
async def list_platforms(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """All platform instances with their platform and account counts."""
    rows = (
        await session.scalars(
            select(PlatformInstance)
            .options(selectinload(PlatformInstance.accounts))
            .order_by(PlatformInstance.id)
        )
    ).all()
    return [_instance_detail(instance, instance.platform.name) for instance in rows]


@router.post("/platforms")
async def create_platform(payload: CreatePlatformRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Create a platform instance after validating its config against the plugin."""
    plugin = plugin_registry.get(payload.platform_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"平台插件未加载: {payload.platform_id}")

    ok, message = plugin.validate_config(payload.config)
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    instance = PlatformInstance(
        platform_id=payload.platform_id,
        name=payload.name,
        base_url=payload.base_url,
        config=payload.config,
        timezone=payload.timezone,
        description=payload.description,
        enabled=payload.enabled,
    )
    instance.accounts = []  # 新实例暂无账号，避免序列化时触发懒加载
    session.add(instance)
    await session.flush()
    return _instance_detail(instance, plugin.plugin_name)


async def _get_instance(session: AsyncSession, instance_id: int) -> PlatformInstance:
    instance = await session.scalar(
        select(PlatformInstance)
        .where(PlatformInstance.id == instance_id)
        .options(selectinload(PlatformInstance.accounts))
    )
    if instance is None:
        raise HTTPException(status_code=404, detail="平台实例不存在")
    return instance


@router.get("/platforms/{instance_id}")
async def get_platform(instance_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    instance = await _get_instance(session, instance_id)
    return _instance_detail(instance, instance.platform.name)


@router.put("/platforms/{instance_id}")
async def update_platform(
    instance_id: int, payload: UpdatePlatformRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Partially update a platform instance; validates config when provided."""
    instance = await _get_instance(session, instance_id)

    if payload.config is not None:
        plugin = plugin_registry.get(instance.platform_id)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"平台插件未加载: {instance.platform_id}")
        ok, message = plugin.validate_config(payload.config)
        if not ok:
            raise HTTPException(status_code=422, detail=message)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(instance, field, value)
    return _instance_detail(instance, instance.platform.name)


@router.delete("/platforms/{instance_id}")
async def delete_platform(instance_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Delete a platform instance; refused while it still has accounts."""
    instance = await _get_instance(session, instance_id)
    if instance.accounts:
        raise HTTPException(status_code=409, detail="该平台实例下仍有账号，请先删除账号")
    await session.delete(instance)
    return {"ok": True}
