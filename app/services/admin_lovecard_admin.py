"""Lovecard templates (相亲卡, A8) service for the back office.

模板条件与生成记录为独立表；卡片出图依赖素材渲染能力（25 套样式模板文件
尚未入库），Phase 1 未接入渲染器，``generate_lovecards`` 一律 fail-closed
503（真实出图在渲染/三方适配阶段落地，见 docs/待完成事项.md）。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin_lovecard_admin import (
    LovecardGenerateRequest,
    LovecardGenerateResult,
    LovecardGenerationItem,
    LovecardGenerationPage,
    LovecardTemplateCreate,
    LovecardTemplateItem,
    LovecardTemplatePage,
    LovecardTemplateUpdate,
)

_TEMPLATE_SELECT = """SELECT t.id, t.name, t.style, t.activity_id, t.register_start, t.register_end,
    t.region_code, t.native_place, t.height_min, t.height_max, t.age_min, t.age_max,
    t.promoter_id, t.matchmaker_id, t.qrcode_desc, t.qrcode_expire_days, t.limit_latest,
    t.tags_json, t.enabled, t.created_by, t.created_at, t.updated_at
    FROM admin_lovecard_template t"""

_GENERATION_SELECT = """SELECT g.id, g.template_id, g.batch_no, g.user_id, u.nickname,
    g.image_url, g.status, g.error, g.generated_by, g.created_at
    FROM admin_lovecard_generation g LEFT JOIN users u ON u.id = g.user_id"""


def _template_item(row: Any) -> LovecardTemplateItem:
    data = dict(row)
    raw_tags = data.pop("tags_json", None)
    if isinstance(raw_tags, str) and raw_tags:
        try:
            data["tags"] = json.loads(raw_tags)
        except (TypeError, ValueError):
            data["tags"] = []
    else:
        data["tags"] = []
    if not isinstance(data["tags"], list):
        data["tags"] = []
    data["enabled"] = bool(int(data["enabled"]))
    return LovecardTemplateItem(**data)


def _generation_item(row: Any) -> LovecardGenerationItem:
    return LovecardGenerationItem(**dict(row))


async def _get_template(db: AsyncSession, template_id: int) -> LovecardTemplateItem:
    row = (
        await db.execute(text(f"{_TEMPLATE_SELECT} WHERE t.id = :id"), {"id": template_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="相亲卡模板不存在")
    return _template_item(row)


async def _require_targets(db: AsyncSession, promoter_id: int | None, matchmaker_id: int | None, activity_id: int | None) -> None:
    """红娘目标必须是有效服务红娘；活动目标必须存在（表缺列时只校验有值的字段）。"""
    valid = "SELECT 1 FROM users x WHERE x.id = :target AND x.status = 1"
    for target_id in {promoter_id, matchmaker_id}:
        if target_id is not None:
            ok = (await db.execute(text(valid + " AND EXISTS (SELECT 1 FROM user_role ur WHERE ur.user_id = x.id AND ur.role_code = 'service_matchmaker' AND ur.status = 1)"), {"target": target_id})).scalar_one_or_none()
            if not ok:
                raise HTTPException(422, detail=f"红娘目标 {target_id} 不是有效服务红娘")
    if activity_id is not None:
        ok = (await db.execute(text("SELECT 1 FROM offline_activity WHERE id = :id"), {"id": activity_id})).scalar_one_or_none()
        if not ok:
            raise HTTPException(422, detail="关联线下活动不存在")


# ─────────────────────────── 模板 ───────────────────────────


async def list_templates(
    db: AsyncSession, page: int, page_size: int, keyword: str | None, enabled: bool | None
) -> LovecardTemplatePage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append("(t.name LIKE :keyword OR t.qrcode_desc LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if enabled is not None:
        where.append("t.enabled = :enabled")
        params["enabled"] = int(enabled)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int((await db.execute(text(f"SELECT COUNT(*) FROM admin_lovecard_template t {where_sql}"), params)).scalar() or 0)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_TEMPLATE_SELECT} {where_sql} ORDER BY t.id DESC LIMIT :limit OFFSET :offset"), params
        )
    ).mappings().all()
    return LovecardTemplatePage(
        items=[_template_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_template(db: AsyncSession, actor_id: int, body: LovecardTemplateCreate) -> LovecardTemplateItem:
    await _require_targets(db, body.promoter_id, body.matchmaker_id, body.activity_id)
    result = await db.execute(
        text(
            "INSERT INTO admin_lovecard_template "
            "(name, style, activity_id, register_start, register_end, region_code, native_place,"
            " height_min, height_max, age_min, age_max, promoter_id, matchmaker_id, qrcode_desc,"
            " qrcode_expire_days, limit_latest, tags_json, enabled, created_by) "
            "VALUES (:name, :style, :activity_id, :register_start, :register_end, :region_code, :native_place,"
            " :height_min, :height_max, :age_min, :age_max, :promoter_id, :matchmaker_id, :qrcode_desc,"
            " :qrcode_expire_days, :limit_latest, :tags_json, :enabled, :created_by)"
        ),
        {
            **body.model_dump(),
            "tags_json": json.dumps(body.tags, ensure_ascii=False),
            "enabled": int(body.enabled),
            "created_by": actor_id,
        },
    )
    item = await _get_template(db, int(result.lastrowid))
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'lovecard_template.create', 'admin_lovecard_template', :id)"
        ),
        {"actor": actor_id, "id": item.id},
    )
    await db.commit()
    return item


async def update_template(db: AsyncSession, actor_id: int, template_id: int, body: LovecardTemplateUpdate) -> LovecardTemplateItem:
    await _get_template(db, template_id)
    values = body.model_dump(exclude_unset=True)
    if "tags" in values:
        values["tags_json"] = json.dumps(values.pop("tags") or [], ensure_ascii=False)
    if "enabled" in values and values["enabled"] is not None:
        values["enabled"] = int(values["enabled"])
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE admin_lovecard_template SET {assignments}, updated_at = UTC_TIMESTAMP() WHERE id = :id"),
            {**values, "id": template_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'lovecard_template.update', 'admin_lovecard_template', :id)"
        ),
        {"actor": actor_id, "id": template_id},
    )
    await db.commit()
    return await _get_template(db, template_id)


async def delete_template(db: AsyncSession, actor_id: int, template_id: int) -> None:
    await _get_template(db, template_id)
    await db.execute(text("DELETE FROM admin_lovecard_template WHERE id = :id"), {"id": template_id})
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'lovecard_template.delete', 'admin_lovecard_template', :id)"
        ),
        {"actor": actor_id, "id": template_id},
    )
    await db.commit()


# ─────────────────────────── 生成 ───────────────────────────


async def generate_lovecards(
    db: AsyncSession, actor_id: int, template_id: int, body: LovecardGenerateRequest
) -> LovecardGenerateResult:
    """批量出图。渲染器未接入，先 fail-closed：校验模板可用后 503，不写生成行。"""
    template = await _get_template(db, template_id)
    if not template.enabled:
        raise HTTPException(409, detail="模板已停用，不能生成")
    _ = template.limit_latest  # limit 在渲染阶段参与取值，此处保持 503 前不产生副作用
    raise HTTPException(503, detail="相亲卡渲染服务未配置，暂不能生成卡片图片")


async def list_generations(
    db: AsyncSession, page: int, page_size: int, template_id: int | None, status: str | None
) -> LovecardGenerationPage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if template_id is not None:
        where.append("g.template_id = :template_id")
        params["template_id"] = template_id
    if status in {"pending", "success", "failed"}:
        where.append("g.status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM admin_lovecard_generation g LEFT JOIN users u ON u.id = g.user_id " + where_sql),
                params,
            )
        ).scalar()
        or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_GENERATION_SELECT} {where_sql} ORDER BY g.id DESC LIMIT :limit OFFSET :offset"), params
        )
    ).mappings().all()
    return LovecardGenerationPage(
        items=[_generation_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )
