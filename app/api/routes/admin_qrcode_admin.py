"""QR code management (二维码管理, A5) routes for the back office."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Path as PathParam, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.admin_qrcode_admin import QrcodeCreate, QrcodeItem, QrcodePage, QrcodeRenew, QrcodeUpdate
from app.services import admin_qrcode_admin as service
from app.services.media_access import MEDIA_CATEGORY_ADMIN, sign_media_url

router = APIRouter(prefix="/admin/qrcodes")


def _sign(url: str | None, viewer: int) -> str | None:
    return sign_media_url(url, category=MEDIA_CATEGORY_ADMIN, viewer=viewer) if url else None


@declare_permission("platform.qrcode.read")
@router.get("", response_model=QrcodePage, summary="二维码列表（分页 + 类型 / 状态 / 创建时间）")
async def qrcodes_list(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=64),
    scene: str | None = Query(None, max_length=32),
    status: int | None = Query(None, ge=0, le=1),
    created_start: str | None = Query(None, max_length=10, description="创建时间起（含）"),
    created_end: str | None = Query(None, max_length=10, description="创建时间止（含）"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> QrcodePage:
    current.require("platform.qrcode.read")
    result = await service.list_qrcodes(db, page, page_size, keyword, scene, status, created_start, created_end)
    for item in result.items:
        item.image_url = _sign(item.image_url, current.account.id) or ""
    return result


@declare_permission("platform.qrcode.write")
@router.post("", response_model=QrcodeItem, status_code=201, summary="生成二维码（scene + 有效期 + 描述）")
async def qrcodes_create(
    body: QrcodeCreate = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> QrcodeItem:
    current.require("platform.qrcode.write")
    # 先出图（provider 不可用时在此 503），再落盘，最后登记行与审计。
    png = await service.render_image(body.type, body.target_url)
    token = uuid.uuid4().hex
    directory = Path(settings.upload_dir) / "admin" / "qrcodes"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{token}.png").write_bytes(png)
    item = await service.create_qrcode(
        db, current.account.id, body, image_url=f"/storage/uploads/admin/qrcodes/{token}.png"
    )
    item.image_url = _sign(item.image_url, current.account.id) or ""
    return item


@declare_permission("platform.qrcode.write")
@router.post("/{qrcode_id}/renew", response_model=QrcodeItem, summary="二维码续期")
async def qrcodes_renew(
    body: QrcodeRenew = ...,
    qrcode_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> QrcodeItem:
    current.require("platform.qrcode.write")
    item = await service.renew_qrcode(db, current.account.id, qrcode_id, body)
    item.image_url = _sign(item.image_url, current.account.id) or ""
    return item


@declare_permission("platform.qrcode.write")
@router.patch("/{qrcode_id}", response_model=QrcodeItem, summary="更新二维码（改名 / 改指向地址）")
async def qrcodes_update(
    body: QrcodeUpdate = ...,
    qrcode_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> QrcodeItem:
    current.require("platform.qrcode.write")
    image_url: str | None = None
    if body.target_url is not None:
        # 指向地址变化后必须重新出图，旧图扫码已指向旧地址。
        # 载体类型沿用既有行（小程序码不能降级成普通二维码）。
        existing = await service.get_qrcode(db, qrcode_id)
        token = uuid.uuid4().hex
        directory = Path(settings.upload_dir) / "admin" / "qrcodes"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{token}.png").write_bytes(
            await service.render_image(existing.type, body.target_url)
        )
        image_url = f"/storage/uploads/admin/qrcodes/{token}.png"
    item = await service.update_qrcode(db, current.account.id, qrcode_id, body, image_url=image_url)
    item.image_url = _sign(item.image_url, current.account.id) or ""
    return item


@declare_permission("platform.qrcode.write")
@router.delete("/{qrcode_id}", status_code=204, summary="删除二维码")
async def qrcodes_delete(
    qrcode_id: int = PathParam(..., ge=1),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    current.require("platform.qrcode.write")
    await service.delete_qrcode(db, current.account.id, qrcode_id)
