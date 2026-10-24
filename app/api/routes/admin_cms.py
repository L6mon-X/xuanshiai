"""A11-CMS：系统更新公告 / 使用帮助文档管理接口。

复用通用内容表 `admin_content_item`（域判别 `update_report` / `help_doc`），**不新建表**：
标题落在 `title`，正文（富文本 / Markdown）与分类等落在 `extra_json` 的 `body` / `category`。
本模块只在前端约定的路径（`/admin/update-reports`、`/admin/help-docs`）上包一层，
读写与校验全部委托 admin_content 服务，避免另造轮子（PROJECT_RULES §2.4）。

权限沿用通用内容域口径：读 `platform.config.read`，写 `platform.config.write`。
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.admin_content import ContentItem, ContentItemCreate, ContentItemPage, ContentItemUpdate
from app.services.admin_content import create_item, delete_item, get_item, list_items, update_item

update_report_router = APIRouter(prefix="/admin/update-reports")
help_doc_router = APIRouter(prefix="/admin/help-docs")

_UPDATE_DOMAIN = "update_report"
_HELP_DOMAIN = "help_doc"


@declare_permission("platform.config.read")
@update_report_router.get("", response_model=ContentItemPage, summary="系统更新公告列表")
async def update_report_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64, description="标题/正文模糊"),
    category: str | None = Query(None, max_length=32, description="按 extra.category 分类筛选"),
    status: int | None = Query(None, ge=1, le=2, description="1 正常 / 2 停用"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItemPage:
    current.require("platform.config.read")
    extra_filters = {"category": category} if category else None
    return await list_items(db, _UPDATE_DOMAIN, page, page_size, keyword, status, extra_filters)


@declare_permission("platform.config.read")
@update_report_router.get("/{item_id}", response_model=ContentItem, summary="系统更新公告详情")
async def update_report_detail(
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.read")
    return await get_item(db, _UPDATE_DOMAIN, item_id)


@declare_permission("platform.config.write")
@update_report_router.post("", response_model=ContentItem, status_code=201, summary="新增系统更新公告")
async def update_report_create(
    body: ContentItemCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.write")
    return await create_item(db, current.account.id, _UPDATE_DOMAIN, body)


@declare_permission("platform.config.write")
@update_report_router.patch("/{item_id}", response_model=ContentItem, summary="更新系统更新公告")
async def update_report_update(
    body: ContentItemUpdate = ...,
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.write")
    return await update_item(db, _UPDATE_DOMAIN, item_id, body)


@declare_permission("platform.config.write")
@update_report_router.delete("/{item_id}", status_code=204, summary="删除系统更新公告")
async def update_report_delete(
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.config.write")
    await delete_item(db, _UPDATE_DOMAIN, item_id)


@declare_permission("platform.config.read")
@help_doc_router.get("", response_model=ContentItemPage, summary="使用帮助文档列表")
async def help_doc_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64, description="标题/正文模糊"),
    status: int | None = Query(None, ge=1, le=2, description="1 正常 / 2 停用"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItemPage:
    current.require("platform.config.read")
    return await list_items(db, _HELP_DOMAIN, page, page_size, keyword, status, None)


@declare_permission("platform.config.read")
@help_doc_router.get("/{item_id}", response_model=ContentItem, summary="使用帮助文档详情")
async def help_doc_detail(
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.read")
    return await get_item(db, _HELP_DOMAIN, item_id)


@declare_permission("platform.config.write")
@help_doc_router.post("", response_model=ContentItem, status_code=201, summary="新增使用帮助文档")
async def help_doc_create(
    body: ContentItemCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.write")
    return await create_item(db, current.account.id, _HELP_DOMAIN, body)


@declare_permission("platform.config.write")
@help_doc_router.patch("/{item_id}", response_model=ContentItem, summary="更新使用帮助文档")
async def help_doc_update(
    body: ContentItemUpdate = ...,
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentItem:
    current.require("platform.config.write")
    return await update_item(db, _HELP_DOMAIN, item_id, body)


@declare_permission("platform.config.write")
@help_doc_router.delete("/{item_id}", status_code=204, summary="删除使用帮助文档")
async def help_doc_delete(
    item_id: int = Path(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.config.write")
    await delete_item(db, _HELP_DOMAIN, item_id)
