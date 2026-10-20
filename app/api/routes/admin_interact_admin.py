"""互动内容（A10）路由：复用 ``admin_content_item`` 的 ``interactive_message`` 域。

不建新表：互动内容（图文/视频/投票等）本质是「运营卡片 + 自由 extra 字段」，与
``admin_content`` 的域模型一致。本路由只固定域并收敛权限码，避免前端直接依赖
通用 ``/admin/content/{domain}`` 的域字符串。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.admin_content import ContentItem, ContentItemCreate, ContentItemPage, ContentItemUpdate
from app.services.admin_content import create_item, delete_item, list_items, update_item

router = APIRouter(prefix="/admin/interact/contents")

DOMAIN = "interactive_message"


@declare_permission("platform.interact.read")
@router.get("", response_model=ContentItemPage, summary="互动内容列表")
async def contents_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    status: int | None = Query(None, ge=1, le=2),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItemPage:
    current.require("platform.interact.read")
    return await list_items(db, DOMAIN, page, page_size, keyword, status)


@declare_permission("platform.interact.write")
@router.post("", response_model=ContentItem, status_code=201, summary="新增互动内容")
async def contents_create(
    body: ContentItemCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.interact.write")
    return await create_item(db, current.account.id, DOMAIN, body)


@declare_permission("platform.interact.write")
@router.patch("/{item_id}", response_model=ContentItem, summary="更新互动内容")
async def contents_update(
    item_id: int = Path(..., ge=1),
    body: ContentItemUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.interact.write")
    return await update_item(db, DOMAIN, item_id, body)


@declare_permission("platform.interact.write")
@router.delete("/{item_id}", status_code=204, summary="删除互动内容")
async def contents_delete(
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.interact.write")
    await delete_item(db, DOMAIN, item_id)
