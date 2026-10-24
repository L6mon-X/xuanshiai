"""Alliance activities (活动联盟, A10) routes for the back office."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path as PathParam, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.admin_alliance_activity import (
    AllianceActivityCreate,
    AllianceActivityItem,
    AllianceActivityPage,
    AllianceActivityUpdate,
)
from app.services import admin_alliance_activity as service

router = APIRouter(prefix="/admin/alliance/activities")


@declare_permission("platform.alliance.read")
@router.get("", response_model=AllianceActivityPage, summary="联盟活动列表")
async def activities_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=128),
    status: int | None = Query(None, ge=1, le=4),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AllianceActivityPage:
    current.require("platform.alliance.read")
    return await service.list_activities(db, page, page_size, keyword, status)


@declare_permission("platform.alliance.write")
@router.post("", response_model=AllianceActivityItem, status_code=201, summary="新增联盟活动")
async def activities_create(
    body: AllianceActivityCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AllianceActivityItem:
    current.require("platform.alliance.write")
    return await service.create_activity(db, current.account.id, body)


@declare_permission("platform.alliance.write")
@router.patch("/{activity_id}", response_model=AllianceActivityItem, summary="更新联盟活动")
async def activities_update(
    activity_id: int = PathParam(..., ge=1),
    body: AllianceActivityUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AllianceActivityItem:
    current.require("platform.alliance.write")
    return await service.update_activity(db, current.account.id, activity_id, body)


@declare_permission("platform.alliance.write")
@router.delete("/{activity_id}", status_code=204, summary="删除联盟活动")
async def activities_delete(
    activity_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.alliance.write")
    await service.delete_activity(db, current.account.id, activity_id)
