"""电话外呼（A6）路由：平台配置 / 余额 / 外显号码 / 外呼名单 / 通话记录。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Path as PathParam, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentMatchmakerAdmin,
    declare_permission,
    get_current_matchmaker_admin,
)
from app.db.session import get_db
from app.schemas.admin_outbound_admin import (
    OutboundBalanceItem,
    OutboundConfig,
    OutboundConfigUpdate,
    OutboundNumberCreate,
    OutboundNumberItem,
    OutboundNumberPage,
    OutboundNumberUpdate,
    OutboundRecordPage,
    OutboundTaskCall,
    OutboundTaskImportResult,
    OutboundTaskItem,
    OutboundTaskPage,
)
from app.services import admin_outbound_admin as service
from app.services.profile import _read_limited

router = APIRouter(prefix="/admin/outbound-call")

_MAX_IMPORT_BYTES = 5 * 1024 * 1024


@declare_permission("platform.outbound.read")
@router.get("/config", response_model=OutboundConfig, summary="外呼平台配置（密钥只回显是否已配置）")
async def outbound_config(
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundConfig:
    current.require("platform.outbound.read")
    return await service.get_config(db)


@declare_permission("platform.outbound.write")
@router.put("/config", response_model=OutboundConfig, summary="更新外呼平台配置（非敏感项）")
async def outbound_config_update(
    body: OutboundConfigUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundConfig:
    current.require("platform.outbound.write")
    return await service.update_config(db, current.account.id, body)


@declare_permission("platform.outbound.read")
@router.get("/balance", response_model=OutboundBalanceItem, summary="外呼账户余额")
async def outbound_balance(
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundBalanceItem:
    current.require("platform.outbound.read")
    return await service.get_balance(db)


@declare_permission("platform.outbound.read")
@router.get("/numbers", response_model=OutboundNumberPage, summary="外显号码池")
async def outbound_numbers(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: int | None = Query(None, ge=0, le=1),
    keyword: str | None = Query(None, max_length=32),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundNumberPage:
    current.require("platform.outbound.read")
    return await service.list_numbers(db, page, page_size, status, keyword)


@declare_permission("platform.outbound.write")
@router.post("/numbers", response_model=OutboundNumberItem, status_code=201, summary="新增外显号码")
async def outbound_number_create(
    body: OutboundNumberCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundNumberItem:
    current.require("platform.outbound.write")
    return await service.create_number(db, current.account.id, body)


@declare_permission("platform.outbound.write")
@router.patch("/numbers/{number_id}", response_model=OutboundNumberItem, summary="更新外显号码")
async def outbound_number_update(
    body: OutboundNumberUpdate = ...,
    number_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundNumberItem:
    current.require("platform.outbound.write")
    return await service.update_number(db, current.account.id, number_id, body)


@declare_permission("platform.outbound.write")
@router.delete("/numbers/{number_id}", status_code=204, summary="删除外显号码")
async def outbound_number_delete(
    number_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.outbound.write")
    await service.delete_number(db, current.account.id, number_id)


@declare_permission("platform.outbound.read")
@router.get("/tasks", response_model=OutboundTaskPage, summary="外呼名单（分页 + 状态 / 红娘）")
async def outbound_tasks(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="pending / calling / done / failed / canceled"),
    matchmaker_id: int | None = Query(None, ge=1),
    keyword: str | None = Query(None, max_length=64),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundTaskPage:
    current.require("platform.outbound.read")
    return await service.list_tasks(db, page, page_size, status, matchmaker_id, keyword)


@declare_permission("platform.outbound.write")
@router.post(
    "/tasks",
    response_model=OutboundTaskImportResult,
    status_code=201,
    summary="导入外呼名单（.xlsx，表头含手机号列）",
)
async def outbound_tasks_import(
    file: UploadFile = File(..., description=".xlsx 名单文件"),
    default_matchmaker_id: int | None = Query(None, ge=1, description="未填红娘列时的默认跟进红娘"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundTaskImportResult:
    current.require("platform.outbound.write")
    data = await _read_limited(file, _MAX_IMPORT_BYTES)
    return await service.import_tasks(
        db,
        current.account.id,
        data=data,
        filename=file.filename or "",
        default_matchmaker_id=default_matchmaker_id,
    )


@declare_permission("platform.outbound.write")
@router.post("/tasks/{task_id}/call", response_model=OutboundTaskItem, summary="对外呼名单发起呼叫")
async def outbound_task_call(
    task_id: int = PathParam(..., ge=1),
    body: OutboundTaskCall | None = Body(None, description="可省略；省略时自动选号"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundTaskItem:
    current.require("platform.outbound.write")
    return await service.call_task(
        db, current.account.id, task_id, body.caller_number if body else None
    )


@declare_permission("platform.outbound.read")
@router.get("/records", response_model=OutboundRecordPage, summary="外呼记录（号码脱敏回显）")
async def outbound_records(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    result: str | None = Query(None, description="connected / no_answer / busy / reject / invalid"),
    matchmaker_id: int | None = Query(None, ge=1),
    start_date: str | None = Query(None, max_length=10),
    end_date: str | None = Query(None, max_length=10),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> OutboundRecordPage:
    current.require("platform.outbound.read")
    return await service.list_records(db, page, page_size, result, matchmaker_id, start_date, end_date)
