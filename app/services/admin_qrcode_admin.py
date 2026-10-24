"""QR code management (二维码管理, A5) service for the back office.

H5 / 关注公众号二维码用 ``qrcode`` 本地渲染 PNG（路由层落盘到
``{upload_dir}/admin/qrcodes/`` 后把相对路径交给本层登记）；小程序码
（type=miniprogram）走微信公众号适配器 ``wechat_mp``，凭据未配置时由适配层
fail-closed 503。
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from typing import Any

import qrcode
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin_qrcode_admin import QrcodeCreate, QrcodeItem, QrcodePage, QrcodeRenew, QrcodeUpdate

_QRCODE_SELECT = """SELECT id, name, scene, type, target_url, description, expire_at, status,
    image_url, renew_count, last_renewed_at, created_by, created_at, updated_at
    FROM admin_qrcode"""


def _item(row: Any) -> QrcodeItem:
    return QrcodeItem(**dict(row))


def render_qrcode_png(target: str) -> bytes:
    """本地渲染 H5 二维码 PNG（路由层负责落盘与回传相对路径）。"""
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.make(target)
    buffer = io.BytesIO()
    qr.make_image().save(buffer, format="PNG")
    return buffer.getvalue()


async def render_image(qrcode_type: str, target: str) -> bytes:
    """按类型产出 PNG：h5/follow 本地渲染，miniprogram 走公众号适配器。"""
    if qrcode_type != "miniprogram":
        return render_qrcode_png(target)
    from app.services.wechat_mp.providers import (
        ensure_wechat_mp_configured,
        get_wechat_mp_provider,
    )

    ensure_wechat_mp_configured()
    # 小程序码的 target_url 视为小程序页面路径，scene 用二维码 ID 前缀不足，
    # 因此固定使用 scene=h5 的落地页语义：由小程序端解析 path 中的查询参数。
    return await get_wechat_mp_provider().fetch_miniprogram_code(target, "h5")


async def get_qrcode(db: AsyncSession, qrcode_id: int) -> QrcodeItem:
    """对外暴露的读取（路由层重新出图时需要沿用既有载体类型）。"""
    return await _get(db, qrcode_id)


async def _get(db: AsyncSession, qrcode_id: int) -> QrcodeItem:
    row = (
        await db.execute(text(f"{_QRCODE_SELECT} WHERE id = :id"), {"id": qrcode_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="二维码不存在")
    return _item(row)


async def list_qrcodes(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None,
    scene: str | None,
    status: int | None,
    created_start: str | None,
    created_end: str | None,
) -> QrcodePage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append("(name LIKE :keyword OR target_url LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if scene:
        where.append("scene = :scene")
        params["scene"] = scene
    if status in (0, 1):
        where.append("status = :status")
        params["status"] = status
    if created_start:
        where.append("created_at >= :created_start")
        params["created_start"] = created_start
    if created_end:
        where.append("created_at < DATE_ADD(:created_end, INTERVAL 1 DAY)")
        params["created_end"] = created_end
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int((await db.execute(text(f"SELECT COUNT(*) FROM admin_qrcode {where_sql}"), params)).scalar() or 0)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_QRCODE_SELECT} {where_sql} ORDER BY id DESC LIMIT :limit OFFSET :offset"), params
        )
    ).mappings().all()
    return QrcodePage(
        items=[_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_qrcode(db: AsyncSession, actor_id: int, body: QrcodeCreate, image_url: str) -> QrcodeItem:
    """登记二维码行。``image_url`` 由路由层落盘后传入（先写文件、后登记，避免孤儿行）。"""
    expire_at = datetime.now(timezone.utc) + timedelta(days=body.expire_days)
    result = await db.execute(
        text(
            "INSERT INTO admin_qrcode (name, scene, type, target_url, description, expire_at, status, image_url, created_by) "
            "VALUES (:name, :scene, :type, :target_url, :description, :expire_at, 1, :image_url, :created_by)"
        ),
        {
            "name": body.name,
            "scene": body.scene,
            "type": body.type,
            "target_url": body.target_url,
            "description": body.description,
            "expire_at": expire_at,
            "image_url": image_url,
            "created_by": actor_id,
        },
    )
    qrcode_id = int(result.lastrowid)
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'qrcode.create', 'admin_qrcode', :id)"
        ),
        {"actor": actor_id, "id": qrcode_id},
    )
    await db.commit()
    return await _get(db, qrcode_id)


async def renew_qrcode(db: AsyncSession, actor_id: int, qrcode_id: int, body: QrcodeRenew) -> QrcodeItem:
    """续期：``expire_at = max(now, 当前失效时间) + days``，同时把状态翻回有效。"""
    await _get(db, qrcode_id)
    await db.execute(
        text(
            "UPDATE admin_qrcode SET expire_at = GREATEST(expire_at, UTC_TIMESTAMP()) + INTERVAL :days DAY, "
            "status = 1, renew_count = renew_count + 1, last_renewed_at = UTC_TIMESTAMP() WHERE id = :id"
        ),
        {"days": body.days, "id": qrcode_id},
    )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'qrcode.renew', 'admin_qrcode', :id)"
        ),
        {"actor": actor_id, "id": qrcode_id},
    )
    await db.commit()
    return await _get(db, qrcode_id)


async def update_qrcode(
    db: AsyncSession, actor_id: int, qrcode_id: int, body: QrcodeUpdate, image_url: str | None = None
) -> QrcodeItem:
    await _get(db, qrcode_id)
    values = body.model_dump(exclude_unset=True)
    # 指向地址变化后旧图内容失效：路由层重渲染并把新图路径一并传入。
    if image_url is not None:
        values["image_url"] = image_url
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE admin_qrcode SET {assignments}, updated_at = UTC_TIMESTAMP() WHERE id = :id"),
            {**values, "id": qrcode_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'qrcode.update', 'admin_qrcode', :id)"
        ),
        {"actor": actor_id, "id": qrcode_id},
    )
    await db.commit()
    return await _get(db, qrcode_id)


async def delete_qrcode(db: AsyncSession, actor_id: int, qrcode_id: int) -> None:
    await _get(db, qrcode_id)
    await db.execute(text("DELETE FROM admin_qrcode WHERE id = :id"), {"id": qrcode_id})
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'qrcode.delete', 'admin_qrcode', :id)"
        ),
        {"actor": actor_id, "id": qrcode_id},
    )
    await db.commit()
