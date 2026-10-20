"""Alliance activities (活动联盟, A10) service for the back office."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin_alliance_activity import (
    AllianceActivityCreate,
    AllianceActivityItem,
    AllianceActivityPage,
    AllianceActivityUpdate,
)

_ACTIVITY_SELECT = """SELECT a.id, a.title, a.cover, a.store_id, o.display_name AS store_name,
    a.start_time, a.end_time, a.address, a.fee, a.capacity, a.intro, a.status, a.sort,
    a.created_by, a.created_at, a.updated_at
    FROM admin_alliance_activity a LEFT JOIN organization o ON o.id = a.store_id"""


def _item(row: Any) -> AllianceActivityItem:
    return AllianceActivityItem(**dict(row))


async def _get(db: AsyncSession, activity_id: int) -> AllianceActivityItem:
    row = (
        await db.execute(text(f"{_ACTIVITY_SELECT} WHERE a.id = :id"), {"id": activity_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="联盟活动不存在")
    return _item(row)


async def _validate_store(db: AsyncSession, store_id: int | None) -> None:
    if store_id is None:
        return
    ok = (
        await db.execute(
            text("SELECT 1 FROM organization WHERE id = :id AND org_type = 'store' AND status = 1"),
            {"id": store_id},
        )
    ).scalar_one_or_none()
    if not ok:
        raise HTTPException(422, detail="主办门店不存在或已停用")


async def list_activities(
    db: AsyncSession, page: int, page_size: int, keyword: str | None, status: int | None
) -> AllianceActivityPage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append("(a.title LIKE :keyword OR a.address LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if status is not None:
        where.append("a.status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int((await db.execute(text(f"SELECT COUNT(*) FROM admin_alliance_activity a {where_sql}"), params)).scalar() or 0)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_ACTIVITY_SELECT} {where_sql} ORDER BY a.sort DESC, a.id DESC LIMIT :limit OFFSET :offset"), params
        )
    ).mappings().all()
    return AllianceActivityPage(
        items=[_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_activity(db: AsyncSession, actor_id: int, body: AllianceActivityCreate) -> AllianceActivityItem:
    await _validate_store(db, body.store_id)
    payload = body.model_dump()
    payload["created_by"] = actor_id
    result = await db.execute(
        text(
            "INSERT INTO admin_alliance_activity "
            "(title, cover, store_id, start_time, end_time, address, fee, capacity, intro, status, sort, created_by) "
            "VALUES (:title, :cover, :store_id, :start_time, :end_time, :address, :fee, :capacity, :intro, :status, :sort, :created_by)"
        ),
        payload,
    )
    item = await _get(db, int(result.lastrowid))
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'alliance_activity.create', 'admin_alliance_activity', :id)"
        ),
        {"actor": actor_id, "id": item.id},
    )
    await db.commit()
    return item


async def update_activity(
    db: AsyncSession, actor_id: int, activity_id: int, body: AllianceActivityUpdate
) -> AllianceActivityItem:
    await _get(db, activity_id)
    values = body.model_dump(exclude_unset=True)
    if "store_id" in values and values["store_id"] is not None:
        await _validate_store(db, values["store_id"])
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE admin_alliance_activity SET {assignments}, updated_at = UTC_TIMESTAMP() WHERE id = :id"),
            {**values, "id": activity_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'alliance_activity.update', 'admin_alliance_activity', :id)"
        ),
        {"actor": actor_id, "id": activity_id},
    )
    await db.commit()
    return await _get(db, activity_id)


async def delete_activity(db: AsyncSession, actor_id: int, activity_id: int) -> None:
    await _get(db, activity_id)
    await db.execute(text("DELETE FROM admin_alliance_activity WHERE id = :id"), {"id": activity_id})
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'alliance_activity.delete', 'admin_alliance_activity', :id)"
        ),
        {"actor": actor_id, "id": activity_id},
    )
    await db.commit()
