"""电子合同（A3）路由：合同 / 模板 / 印章 / 配置。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Path as PathParam, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentMatchmakerAdmin,
    declare_permission,
    get_current_matchmaker_admin,
    require_sensitive_operation,
)
from app.core.config import settings
from app.db.session import get_db
from app.schemas.admin_econtract_admin import (
    EcontractConfig,
    EcontractConfigUpdate,
    EcontractCreate,
    EcontractDetail,
    EcontractPage,
    EcontractSealCreate,
    EcontractSealItem,
    EcontractSealUpdate,
    EcontractTemplateCreate,
    EcontractTemplateItem,
    EcontractTemplatePage,
    EcontractTemplateUpdate,
    EcontractVoidRequest,
)
from app.services import admin_econtract_admin as service
from app.services.media_access import MEDIA_CATEGORY_ADMIN, sign_media_url
from app.services.profile import IMAGE_MAX_BYTES, _image_outputs, _read_limited
from app.services.sensitive_operations import (
    abort_sensitive_operation,
    begin_sensitive_operation,
    finish_sensitive_operation,
)

router = APIRouter(prefix="/admin")


def _sign(url: str | None, viewer: int) -> str | None:
    return sign_media_url(url, category=MEDIA_CATEGORY_ADMIN, viewer=viewer) if url else None


# ─────────────────────────── 配置 ───────────────────────────


@declare_permission("finance.contract.read")
@router.get("/e-contract-config", response_model=EcontractConfig, summary="电子签配置（密钥只回显是否已配置）")
async def econtract_config(
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractConfig:
    current.require("finance.contract.read")
    return await service.get_config(db)


@declare_permission("finance.contract.write")
@router.put("/e-contract-config", response_model=EcontractConfig, summary="更新电子签配置（非敏感项）")
async def econtract_config_update(
    body: EcontractConfigUpdate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractConfig:
    current.require("finance.contract.write")
    return await service.update_config(db, current.account.id, body)


# ─────────────────────────── 合同 ───────────────────────────


@declare_permission("finance.contract.read")
@router.get("/e-contracts", response_model=EcontractPage, summary="合同列表（分页 + 状态 / 模板 / 日期）")
async def econtracts_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    status: str | None = Query(None, description="draft / signing / signed / voided / expired"),
    template_id: int | None = Query(None, ge=1),
    start_date: str | None = Query(None, max_length=10),
    end_date: str | None = Query(None, max_length=10),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractPage:
    current.require("finance.contract.read")
    return await service.list_contracts(
        db, page, page_size, keyword, status, template_id, start_date, end_date
    )


@declare_permission("finance.contract.write")
@router.post("/e-contracts", response_model=EcontractDetail, status_code=201, summary="发起合同")
async def econtracts_create(
    body: EcontractCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractDetail:
    current.require("finance.contract.write")
    return await service.create_contract(db, current.account.id, body)


@declare_permission("finance.contract.read")
@router.get("/e-contracts/{contract_id}", response_model=EcontractDetail, summary="合同详情（含签署流水）")
async def econtracts_detail(
    contract_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractDetail:
    current.require("finance.contract.read")
    return await service.get_contract(db, contract_id)


@declare_permission("finance.contract.write")
@router.post(
    "/e-contracts/{contract_id}/void",
    response_model=EcontractDetail,
    summary="作废合同（幂等 + 二次确认）",
)
async def econtracts_void(
    body: EcontractVoidRequest = ...,
    contract_id: int = PathParam(..., ge=1),
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractDetail:
    current.require("finance.contract.write")
    reservation, replayed = await begin_sensitive_operation(
        db,
        actor_id=current.account.id,
        operation="admin.econtract.void",
        idempotency_key=idempotency_key,
        payload={"contract_id": contract_id, "reason": body.reason},
    )
    if replayed is not None:
        return EcontractDetail(**replayed)
    try:
        result = await service.void_contract(db, current.account.id, contract_id, body)
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    await finish_sensitive_operation(db, reservation, result.model_dump(mode="json"))
    return result


# ─────────────────────────── 模板 ───────────────────────────


@declare_permission("finance.contract.read")
@router.get(
    "/e-contract-templates", response_model=EcontractTemplatePage, summary="合同模板列表"
)
async def econtract_templates(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    contract_type: str | None = Query(None, max_length=64),
    status: int | None = Query(None, ge=0, le=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractTemplatePage:
    current.require("finance.contract.read")
    return await service.list_templates(db, page, page_size, keyword, contract_type, status)


@declare_permission("finance.contract.write")
@router.post(
    "/e-contract-templates",
    response_model=EcontractTemplateItem,
    status_code=201,
    summary="新增合同模板",
)
async def econtract_template_create(
    body: EcontractTemplateCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractTemplateItem:
    current.require("finance.contract.write")
    return await service.create_template(db, current.account.id, body)


@declare_permission("finance.contract.write")
@router.patch(
    "/e-contract-templates/{template_id}",
    response_model=EcontractTemplateItem,
    summary="更新合同模板",
)
async def econtract_template_update(
    body: EcontractTemplateUpdate = ...,
    template_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractTemplateItem:
    current.require("finance.contract.write")
    return await service.update_template(db, current.account.id, template_id, body)


@declare_permission("finance.contract.write")
@router.delete("/e-contract-templates/{template_id}", status_code=204, summary="删除合同模板")
async def econtract_template_delete(
    template_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("finance.contract.write")
    await service.delete_template(db, current.account.id, template_id)


# ─────────────────────────── 印章 ───────────────────────────


@declare_permission("finance.contract.read")
@router.get("/e-contract-seals", response_model=list[EcontractSealItem], summary="电子印章列表")
async def econtract_seals(
    status: int | None = Query(None, ge=0, le=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> list[EcontractSealItem]:
    current.require("finance.contract.read")
    items = await service.list_seals(db, status)
    for item in items:
        item.image_url = _sign(item.image_url, current.account.id) or ""
    return items


@declare_permission("finance.contract.write")
@router.post(
    "/e-contract-seals",
    response_model=EcontractSealItem,
    status_code=201,
    summary="新增印章（上传图片或传已有图片地址）",
)
async def econtract_seal_create(
    name: str = Query(..., min_length=1, max_length=128),
    seal_type: str = Query("company", pattern="^(company|personal)$"),
    authorized_person: str | None = Query(None, max_length=64),
    image_url: str | None = Query(None, max_length=500, description="已有图片地址，与 file 二选一"),
    file: UploadFile | None = File(None, description="印章图片（png/jpg），≤5MB"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractSealItem:
    current.require("finance.contract.write")
    final_url = image_url
    if file is not None:
        data = await _read_limited(file, IMAGE_MAX_BYTES)
        webp, _thumb = _image_outputs(data)
        token = uuid.uuid4().hex
        directory = Path(settings.upload_dir) / "admin" / "econtract-seals"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{token}.webp").write_bytes(webp)
        final_url = f"/storage/uploads/admin/econtract-seals/{token}.webp"
    if not final_url:
        raise HTTPException(422, detail="必须上传印章图片或提供 image_url")
    body = EcontractSealCreate(
        name=name,
        seal_type=seal_type,
        image_url=final_url,
        authorized_person=authorized_person,
    )
    item = await service.create_seal(db, current.account.id, body)
    item.image_url = _sign(item.image_url, current.account.id) or ""
    return item


@declare_permission("finance.contract.write")
@router.patch("/e-contract-seals/{seal_id}", response_model=EcontractSealItem, summary="更新印章")
async def econtract_seal_update(
    body: EcontractSealUpdate = ...,
    seal_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> EcontractSealItem:
    current.require("finance.contract.write")
    item = await service.update_seal(db, current.account.id, seal_id, body)
    item.image_url = _sign(item.image_url, current.account.id) or ""
    return item


@declare_permission("finance.contract.write")
@router.delete("/e-contract-seals/{seal_id}", status_code=204, summary="删除印章")
async def econtract_seal_delete(
    seal_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("finance.contract.write")
    await service.delete_seal(db, current.account.id, seal_id)
