"""Lovecard templates (相亲卡, A8) routes for the back office."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path as PathParam, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.admin_lovecard_admin import (
    LovecardGenerateRequest,
    LovecardGenerateResult,
    LovecardGenerationPage,
    LovecardTemplateCreate,
    LovecardTemplateItem,
    LovecardTemplatePage,
    LovecardTemplateUpdate,
)
from app.services import admin_lovecard_admin as service
from app.services.media_access import MEDIA_CATEGORY_ADMIN, sign_media_url

router = APIRouter(prefix="/admin/lovecard-templates")


def _sign(url: str | None, viewer: int) -> str | None:
    return sign_media_url(url, category=MEDIA_CATEGORY_ADMIN, viewer=viewer) if url else None


@declare_permission("platform.lovecard.read")
@router.get("", response_model=LovecardTemplatePage, summary="相亲卡模板列表")
async def templates_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    enabled: bool | None = Query(None),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LovecardTemplatePage:
    current.require("platform.lovecard.read")
    return await service.list_templates(db, page, page_size, keyword, enabled)


@declare_permission("platform.lovecard.write")
@router.post("", response_model=LovecardTemplateItem, status_code=201, summary="新增相亲卡模板")
async def templates_create(
    body: LovecardTemplateCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LovecardTemplateItem:
    current.require("platform.lovecard.write")
    return await service.create_template(db, current.account.id, body)


# 静态路径先于 /{template_id}
@declare_permission("platform.lovecard.read")
@router.get("/generations", response_model=LovecardGenerationPage, summary="相亲卡生成记录（分页 + 模板 / 状态）")
async def generations_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    template_id: int | None = Query(None, ge=1),
    status: str | None = Query(None, max_length=16),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LovecardGenerationPage:
    current.require("platform.lovecard.read")
    result = await service.list_generations(db, page, page_size, template_id, status)
    for item in result.items:
        if item.image_url:
            item.image_url = _sign(item.image_url, current.account.id)
    return result


@declare_permission("platform.lovecard.write")
@router.patch("/{template_id}", response_model=LovecardTemplateItem, summary="更新相亲卡模板")
async def templates_update(
    template_id: int = PathParam(..., ge=1),
    body: LovecardTemplateUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LovecardTemplateItem:
    current.require("platform.lovecard.write")
    return await service.update_template(db, current.account.id, template_id, body)


@declare_permission("platform.lovecard.write")
@router.post("/{template_id}/generate", response_model=LovecardGenerateResult, summary="按模板批量生成相亲卡")
async def templates_generate(
    body: LovecardGenerateRequest = ...,
    template_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LovecardGenerateResult:
    current.require("platform.lovecard.write")
    result = await service.generate_lovecards(db, current.account.id, template_id, body)
    result.images = [url for url in result.images if url]
    return result


@declare_permission("platform.lovecard.write")
@router.delete("/{template_id}", status_code=204, summary="删除相亲卡模板")
async def templates_delete(
    template_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.lovecard.write")
    await service.delete_template(db, current.account.id, template_id)
