"""Cloud material library (云端素材库, A4) routes for the back office."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Path as PathParam, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.admin_material_admin import (
    MaterialCategoryCreate,
    MaterialCategoryItem,
    MaterialCategoryPage,
    MaterialCategoryUpdate,
    MaterialItem,
    MaterialPage,
    MaterialUpdate,
    MaterialUploadResponse,
)
from app.services import admin_material_admin as service
from app.services.media_access import MEDIA_CATEGORY_ADMIN, sign_media_url
from app.services.profile import IMAGE_MAX_BYTES, _image_outputs, _read_limited

router = APIRouter(prefix="/admin/materials")


def _signed(items: list[MaterialItem], viewer: int) -> list[MaterialItem]:
    """素材列表返回现签的临时访问地址，DB 内仍存相对路径。"""
    for item in items:
        if item.url:
            item.url = sign_media_url(item.url, category=MEDIA_CATEGORY_ADMIN, viewer=viewer)
        if item.thumbnail_url:
            item.thumbnail_url = sign_media_url(item.thumbnail_url, category=MEDIA_CATEGORY_ADMIN, viewer=viewer)
    return items


@declare_permission("platform.material.read")
@router.get("", response_model=MaterialPage, summary="素材列表（分页 + 分类 / 关键词）")
async def materials_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    category_id: int | None = Query(None, ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialPage:
    current.require("platform.material.read")
    result = await service.list_materials(db, page, page_size, keyword, category_id)
    result.items = _signed(result.items, current.account.id)
    return result


@declare_permission("platform.material.write")
@router.post("", response_model=MaterialUploadResponse, status_code=201, summary="上传素材（multipart 图片）")
async def materials_upload(
    category_id: int = Query(..., ge=1),
    file: UploadFile = File(...),
    name: str | None = Query(None, max_length=128),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialUploadResponse:
    current.require("platform.material.write")
    data = await _read_limited(file, IMAGE_MAX_BYTES)
    image_data, thumbnail_data = _image_outputs(data)
    directory = Path(settings.upload_dir) / "admin"
    directory.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    (directory / f"{token}.webp").write_bytes(image_data)
    (directory / f"{token}-thumb.webp").write_bytes(thumbnail_data)
    item = await service.register_material(
        db,
        current.account.id,
        category_id=category_id,
        name=name or f"素材-{token[:8]}",
        url=f"/storage/uploads/admin/{token}.webp",
        thumbnail_url=f"/storage/uploads/admin/{token}-thumb.webp",
        mime_type="image/webp",
        size=len(image_data),
        width=None,
        height=None,
    )
    return MaterialUploadResponse(
        id=item.id,
        name=item.name,
        url=sign_media_url(item.url, category=MEDIA_CATEGORY_ADMIN, viewer=current.account.id),
        thumbnail_url=sign_media_url(item.thumbnail_url, category=MEDIA_CATEGORY_ADMIN, viewer=current.account.id),
        mime_type=item.mime_type,
        size=item.size,
    )


@declare_permission("platform.material.write")
@router.patch("/{material_id}", response_model=MaterialItem, summary="素材改名 / 移动分类")
async def materials_update(
    material_id: int = PathParam(..., ge=1),
    body: MaterialUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialItem:
    current.require("platform.material.write")
    item = await service.update_material(db, current.account.id, material_id, body)
    item = _signed([item], current.account.id)[0]
    return item


@declare_permission("platform.material.write")
@router.delete("/{material_id}", status_code=204, summary="删除素材（软删）")
async def materials_delete(
    material_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.material.write")
    await service.delete_material(db, current.account.id, material_id)


# 静态路径先于 /{id}
@declare_permission("platform.material.read")
@router.get("/categories", response_model=MaterialCategoryPage, summary="素材分类列表（分页 + 关键词）")
async def categories_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(100, ge=1, le=200),
    keyword: str | None = Query(None, max_length=64),
    parent_id: int | None = Query(None, ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialCategoryPage:
    current.require("platform.material.read")
    return await service.list_categories(db, page, page_size, keyword, parent_id)


@declare_permission("platform.material.write")
@router.post("/categories", response_model=MaterialCategoryItem, status_code=201, summary="新增素材分类")
async def categories_create(
    body: MaterialCategoryCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialCategoryItem:
    current.require("platform.material.write")
    return await service.create_category(db, current.account.id, body)


@declare_permission("platform.material.write")
@router.patch("/categories/{category_id}", response_model=MaterialCategoryItem, summary="更新素材分类")
async def categories_update(
    category_id: int = PathParam(..., ge=1),
    body: MaterialCategoryUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MaterialCategoryItem:
    current.require("platform.material.write")
    return await service.update_category(db, current.account.id, category_id, body)


@declare_permission("platform.material.write")
@router.delete("/categories/{category_id}", status_code=204, summary="删除素材分类")
async def categories_delete(
    category_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.material.write")
    await service.delete_category(db, current.account.id, category_id)
