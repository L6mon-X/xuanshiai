"""Sales library (销售话术库, A7) routes for the back office."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path as PathParam, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.admin_sales_admin import (
    SalesCategoryCreate,
    SalesCategoryItem,
    SalesCategoryPage,
    SalesCategoryUpdate,
    SalesItemCreate,
    SalesItemItem,
    SalesItemPage,
    SalesItemPush,
    SalesItemPushResult,
    SalesItemUpdate,
    SalesPushRecordPage,
)
from app.services import admin_sales_admin as service

router = APIRouter(prefix="/admin/sales-library")


# ─────────────────────────── 分类 ───────────────────────────


@declare_permission("platform.sales.read")
@router.get("/categories", response_model=SalesCategoryPage, summary="话术分类列表")
async def categories_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(100, ge=1, le=200),
    keyword: str | None = Query(None, max_length=64),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesCategoryPage:
    current.require("platform.sales.read")
    return await service.list_categories(db, page, page_size, keyword)


@declare_permission("platform.sales.write")
@router.post("/categories", response_model=SalesCategoryItem, status_code=201, summary="新增话术分类")
async def categories_create(
    body: SalesCategoryCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesCategoryItem:
    current.require("platform.sales.write")
    return await service.create_category(db, current.account.id, body)


@declare_permission("platform.sales.write")
@router.patch("/categories/{category_id}", response_model=SalesCategoryItem, summary="更新话术分类")
async def categories_update(
    category_id: int = PathParam(..., ge=1),
    body: SalesCategoryUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesCategoryItem:
    current.require("platform.sales.write")
    return await service.update_category(db, current.account.id, category_id, body)


@declare_permission("platform.sales.write")
@router.delete("/categories/{category_id}", status_code=204, summary="删除话术分类")
async def categories_delete(
    category_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.sales.write")
    await service.delete_category(db, current.account.id, category_id)


# ─────────────────────────── 话术条目 ───────────────────────────


@declare_permission("platform.sales.read")
@router.get("/items", response_model=SalesItemPage, summary="话术条目列表")
async def items_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    category_id: int | None = Query(None, ge=1),
    status: int | None = Query(None, ge=0, le=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesItemPage:
    current.require("platform.sales.read")
    return await service.list_items(db, page, page_size, keyword, category_id, status)


@declare_permission("platform.sales.write")
@router.post("/items", response_model=SalesItemItem, status_code=201, summary="新增话术条目")
async def items_create(
    body: SalesItemCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesItemItem:
    current.require("platform.sales.write")
    return await service.create_item(db, current.account.id, body)


@declare_permission("platform.sales.write")
@router.post("/items/{item_id}/push", response_model=SalesItemPushResult, summary="话术下发给红娘")
async def items_push(
    item_id: int = PathParam(..., ge=1),
    body: SalesItemPush = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesItemPushResult:
    current.require("platform.sales.write")
    return await service.push_item(db, current.account.id, item_id, body)


@declare_permission("platform.sales.read")
@router.get("/items/push-records", response_model=SalesPushRecordPage, summary="话术下发记录")
async def items_push_records(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    item_id: int | None = Query(None, ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesPushRecordPage:
    current.require("platform.sales.read")
    return await service.list_push_records(db, page, page_size, item_id)


@declare_permission("platform.sales.write")
@router.patch("/items/{item_id}", response_model=SalesItemItem, summary="更新话术条目")
async def items_update(
    item_id: int = PathParam(..., ge=1),
    body: SalesItemUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> SalesItemItem:
    current.require("platform.sales.write")
    return await service.update_item(db, current.account.id, item_id, body)


@declare_permission("platform.sales.write")
@router.delete("/items/{item_id}", status_code=204, summary="删除话术条目（软删）")
async def items_delete(
    item_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.sales.write")
    await service.delete_item(db, current.account.id, item_id)
