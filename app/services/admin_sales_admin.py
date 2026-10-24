"""Sales library (销售话术库, A7) service for the back office.

分类与条目为平台级全局配置（受权限码约束，不随数据范围收敛）；「下发」
校验目标红娘必须为有效服务红娘（users 在 user_role 内持
``service_matchmaker`` 角色且账号启用），逐个写入 ``admin_sales_push``。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    SalesPushRecordItem,
    SalesPushRecordPage,
)

_CATEGORY_SELECT = """SELECT c.id, c.name, c.sort, c.enabled, c.created_at,
    (SELECT COUNT(*) FROM admin_sales_item i WHERE i.category_id = c.id AND i.deleted_at IS NULL) item_count
    FROM admin_sales_category c"""

_ITEM_SELECT = """SELECT i.id, i.category_id, c.name AS category_name, i.title, i.content,
    i.media_url, i.pick_limit, i.status, i.sort, i.created_by, i.created_at, i.updated_at
    FROM admin_sales_item i LEFT JOIN admin_sales_category c ON c.id = i.category_id"""


def _category_item(row: Any) -> SalesCategoryItem:
    data = dict(row)
    data["enabled"] = bool(int(data["enabled"]))
    data["item_count"] = int(data.get("item_count") or 0)
    return SalesCategoryItem(**data)


def _item_item(row: Any) -> SalesItemItem:
    data = dict(row)
    data["status"] = int(data.get("status") or 0)
    return SalesItemItem(**data)


# ─────────────────────────── 分类 ───────────────────────────


async def _get_category(db: AsyncSession, category_id: int) -> SalesCategoryItem:
    row = (
        await db.execute(text(f"{_CATEGORY_SELECT} WHERE c.id = :id"), {"id": category_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="话术分类不存在")
    return _category_item(row)


async def list_categories(
    db: AsyncSession, page: int, page_size: int, keyword: str | None
) -> SalesCategoryPage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append("c.name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int((await db.execute(text(f"SELECT COUNT(*) FROM admin_sales_category c {where_sql}"), params)).scalar() or 0)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_CATEGORY_SELECT} {where_sql} ORDER BY c.sort, c.id LIMIT :limit OFFSET :offset"), params
        )
    ).mappings().all()
    return SalesCategoryPage(
        items=[_category_item(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_category(db: AsyncSession, actor_id: int, body: SalesCategoryCreate) -> SalesCategoryItem:
    result = await db.execute(
        text("INSERT INTO admin_sales_category (name, sort, enabled) VALUES (:name, :sort, :enabled)"),
        {"name": body.name, "sort": body.sort, "enabled": int(body.enabled)},
    )
    item = await _get_category(db, int(result.lastrowid))
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_category.create', 'admin_sales_category', :id)"
        ),
        {"actor": actor_id, "id": item.id},
    )
    await db.commit()
    return item


async def update_category(db: AsyncSession, actor_id: int, category_id: int, body: SalesCategoryUpdate) -> SalesCategoryItem:
    await _get_category(db, category_id)
    values = body.model_dump(exclude_unset=True)
    if "enabled" in values and values["enabled"] is not None:
        values["enabled"] = int(values["enabled"])
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE admin_sales_category SET {assignments} WHERE id = :id"),
            {**values, "id": category_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_category.update', 'admin_sales_category', :id)"
        ),
        {"actor": actor_id, "id": category_id},
    )
    await db.commit()
    return await _get_category(db, category_id)


async def delete_category(db: AsyncSession, actor_id: int, category_id: int) -> None:
    item = await _get_category(db, category_id)
    if item.item_count:
        raise HTTPException(409, detail="分类下还有话术条目，不能删除")
    await db.execute(text("DELETE FROM admin_sales_category WHERE id = :id"), {"id": category_id})
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_category.delete', 'admin_sales_category', :id)"
        ),
        {"actor": actor_id, "id": category_id},
    )
    await db.commit()


# ─────────────────────────── 话术条目 ───────────────────────────


async def _get_item(db: AsyncSession, item_id: int) -> SalesItemItem:
    row = (
        await db.execute(
            text(
                _ITEM_SELECT
                + " WHERE i.id = :id AND i.deleted_at IS NULL"
            ),
            {"id": item_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="话术条目不存在")
    return _item_item(row)


async def list_items(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None,
    category_id: int | None,
    status: int | None,
) -> SalesItemPage:
    where: list[str] = ["i.deleted_at IS NULL"]
    params: dict[str, Any] = {}
    if keyword:
        where.append("(i.title LIKE :keyword OR i.content LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if category_id is not None:
        where.append("i.category_id = :category_id")
        params["category_id"] = category_id
    if status in (0, 1):
        where.append("i.status = :status")
        params["status"] = status
    where_sql = " AND ".join(where)
    total = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM admin_sales_item i "
                    f"LEFT JOIN admin_sales_category c ON c.id = i.category_id WHERE {where_sql}"
                ),
                params,
            )
        ).scalar()
        or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(
                f"{_ITEM_SELECT} WHERE {where_sql} ORDER BY i.sort, i.id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return SalesItemPage(
        items=[_item_item(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_item(db: AsyncSession, actor_id: int, body: SalesItemCreate) -> SalesItemItem:
    exists = (
        await db.execute(
            text("SELECT 1 FROM admin_sales_category WHERE id = :id"),
            {"id": body.category_id},
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(422, detail="话术分类不存在")
    result = await db.execute(
        text(
            "INSERT INTO admin_sales_item (category_id, title, content, media_url, pick_limit, sort, created_by) "
            "VALUES (:category_id, :title, :content, :media_url, :pick_limit, :sort, :created_by)"
        ),
        {
            "category_id": body.category_id,
            "title": body.title,
            "content": body.content,
            "media_url": body.media_url,
            "pick_limit": body.pick_limit,
            "sort": body.sort,
            "created_by": actor_id,
        },
    )
    item = await _get_item(db, int(result.lastrowid))
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_item.create', 'admin_sales_item', :id)"
        ),
        {"actor": actor_id, "id": item.id},
    )
    await db.commit()
    return item


async def update_item(db: AsyncSession, actor_id: int, item_id: int, body: SalesItemUpdate) -> SalesItemItem:
    await _get_item(db, item_id)
    values = body.model_dump(exclude_unset=True)
    if "category_id" in values and values["category_id"] is not None:
        exists = (
            await db.execute(text("SELECT 1 FROM admin_sales_category WHERE id = :id"), {"id": values["category_id"]})
        ).scalar_one_or_none()
        if not exists:
            raise HTTPException(422, detail="目标话术分类不存在")
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(f"UPDATE admin_sales_item SET {assignments}, updated_at = UTC_TIMESTAMP() WHERE id = :id"),
            {**values, "id": item_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_item.update', 'admin_sales_item', :id)"
        ),
        {"actor": actor_id, "id": item_id},
    )
    await db.commit()
    return await _get_item(db, item_id)


async def delete_item(db: AsyncSession, actor_id: int, item_id: int) -> None:
    await _get_item(db, item_id)
    await db.execute(
        text("UPDATE admin_sales_item SET deleted_at = UTC_TIMESTAMP() WHERE id = :id"), {"id": item_id}
    )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'sales_item.delete', 'admin_sales_item', :id)"
        ),
        {"actor": actor_id, "id": item_id},
    )
    await db.commit()


# ─────────────────────────── 下发 ───────────────────────────


_MATCHMAKER_VALID_SQL = """SELECT 1 FROM users u WHERE u.id = :mid AND u.status = 1
    AND EXISTS (SELECT 1 FROM user_role ur WHERE ur.user_id = u.id
        AND ur.role_code = 'service_matchmaker' AND ur.status = 1)"""


async def push_item(db: AsyncSession, actor_id: int, item_id: int, body: SalesItemPush) -> SalesItemPushResult:
    item = await _get_item(db, item_id)
    pushed: list[int] = []
    skipped: list[dict] = []
    for matchmaker_id in dict.fromkeys(body.matchmaker_ids):
        ok = (
            await db.execute(text(_MATCHMAKER_VALID_SQL), {"mid": matchmaker_id})
        ).scalar_one_or_none()
        if not ok:
            skipped.append({"matchmaker_id": matchmaker_id, "reason": "非有效服务红娘"})
            continue
        await db.execute(
            text(
                "INSERT INTO admin_sales_push (item_id, matchmaker_id, note, pushed_by) "
                "VALUES (:item_id, :matchmaker_id, :note, :pushed_by)"
            ),
            {"item_id": item_id, "matchmaker_id": matchmaker_id, "note": body.note, "pushed_by": actor_id},
        )
        pushed.append(matchmaker_id)
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason) "
            "VALUES (:actor, 'sales_item.push', 'admin_sales_item', :id, :reason)"
        ),
        {"actor": actor_id, "id": item_id, "reason": f"下发 {len(pushed)}/{len(set(body.matchmaker_ids))} 条红娘"},
    )
    await db.commit()
    return SalesItemPushResult(item_id=item.id, pushed=pushed, skipped=skipped)


async def list_push_records(
    db: AsyncSession, page: int, page_size: int, item_id: int | None
) -> SalesPushRecordPage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if item_id is not None:
        where.append("p.item_id = :item_id")
        params["item_id"] = item_id
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM admin_sales_push p LEFT JOIN admin_sales_item i ON i.id = p.item_id "
                    f"{where_sql}"
                ),
                params,
            )
        ).scalar()
        or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(
                "SELECT p.id, p.item_id, i.title AS item_title, p.matchmaker_id, u.nickname AS matchmaker_name,"
                " p.note, p.pushed_by, p.created_at"
                " FROM admin_sales_push p LEFT JOIN admin_sales_item i ON i.id = p.item_id"
                " LEFT JOIN users u ON u.id = p.matchmaker_id"
                f" {where_sql} ORDER BY p.id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return SalesPushRecordPage(
        items=[SalesPushRecordItem(**dict(r)) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )
