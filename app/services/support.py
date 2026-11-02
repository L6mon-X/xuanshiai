"""C 端反馈 / 意见箱与帮助中心（Q54，2026-11-02）。

不复用 ``admin_ticket``：其 ``submitter_user_id`` 语义是后台管理员，C 端反馈
混入会污染管理端工单列表。因此新建 ``user_feedback``（迁移
``20261102_01_user_feedback``）并单独提供管理端列表/回复。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import consume_daily, daily_quota_key
from app.schemas.support import (
    AdminFeedbackItem,
    AdminFeedbackPage,
    FeedbackItem,
    FeedbackPage,
    HelpDocItem,
    HelpDocPage,
)

DAILY_FEEDBACK_LIMIT = 10
_DAILY_KEY_PREFIX = "support:feedback"

_ITEM_COLUMNS = (
    "id, category, content, images_json, contact_phone, status, "
    "reply_content, replied_at, created_at"
)


def _parse_images(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _item(row: Any) -> FeedbackItem:
    data = dict(row)
    data["images"] = _parse_images(data.pop("images_json", None))
    return FeedbackItem.model_validate(data)


def _admin_item(row: Any) -> AdminFeedbackItem:
    data = dict(row)
    data["images"] = _parse_images(data.pop("images_json", None))
    return AdminFeedbackItem.model_validate(data)


async def create_feedback(
    db: AsyncSession,
    user_id: int,
    *,
    category: str,
    content: str,
    images: list[str],
    contact_phone: str | None,
) -> FeedbackItem:
    """写入一条反馈；每用户每日最多 10 条（429）。"""
    allowed = await consume_daily(
        daily_quota_key(_DAILY_KEY_PREFIX, user_id), DAILY_FEEDBACK_LIMIT
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="今日反馈次数已达上限（10 条）")

    result = await db.execute(
        text(
            "INSERT INTO user_feedback (user_id, category, content, images_json, contact_phone) "
            "VALUES (:user_id, :category, :content, :images_json, :contact_phone)"
        ),
        {
            "user_id": user_id,
            "category": category,
            "content": content,
            "images_json": json.dumps(images, ensure_ascii=False) if images else None,
            "contact_phone": contact_phone,
        },
    )
    feedback_id = int(result.lastrowid)
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'support.feedback.create', 'user_feedback', :id)"
        ),
        {"actor": user_id, "id": feedback_id},
    )
    await db.commit()
    return await get_my_feedback(db, user_id, feedback_id)


async def get_my_feedback(db: AsyncSession, user_id: int, feedback_id: int) -> FeedbackItem:
    result = await db.execute(
        text(f"SELECT {_ITEM_COLUMNS} FROM user_feedback WHERE id = :id AND user_id = :user_id"),
        {"id": feedback_id, "user_id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return _item(row)


async def list_my_feedback(
    db: AsyncSession, user_id: int, page: int, page_size: int
) -> FeedbackPage:
    params = {"user_id": user_id, "limit": page_size, "offset": (page - 1) * page_size}
    total = int(
        (
            await db.execute(
                text("SELECT COUNT(*) FROM user_feedback WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
        ).scalar()
        or 0
    )
    rows = (
        await db.execute(
            text(
                f"SELECT {_ITEM_COLUMNS} FROM user_feedback WHERE user_id = :user_id "
                "ORDER BY id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return FeedbackPage(
        items=[_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def list_help_docs(
    db: AsyncSession, page: int, page_size: int, keyword: str | None = None
) -> HelpDocPage:
    where = ["tenant_id = 1", "domain = 'help_doc'", "status = 1"]
    params: dict[str, Any] = {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if keyword:
        where.append("(title LIKE :kw OR subtitle LIKE :kw OR extra_json LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    clause = " AND ".join(where)
    total = int(
        (
            await db.execute(
                text(f"SELECT COUNT(*) FROM admin_content_item WHERE {clause}"), params
            )
        ).scalar()
        or 0
    )
    rows = (
        await db.execute(
            text(
                "SELECT id, title, subtitle, extra_json, updated_at FROM admin_content_item "
                f"WHERE {clause} ORDER BY sort DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()

    items: list[HelpDocItem] = []
    for row in rows:
        extra: dict[str, Any] = {}
        try:
            parsed = json.loads(row.get("extra_json") or "{}")
            if isinstance(parsed, dict):
                extra = parsed
        except (TypeError, ValueError):
            extra = {}
        items.append(
            HelpDocItem(
                id=int(row["id"]),
                title=str(row.get("title") or ""),
                subtitle=row.get("subtitle"),
                category=extra.get("category"),
                body=extra.get("body"),
                updated_at=row.get("updated_at"),
            )
        )
    return HelpDocPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


_ADMIN_COLUMNS = (
    "f.id, f.user_id, f.category, f.content, f.images_json, f.contact_phone, f.status, "
    "f.reply_content, f.replied_by, f.replied_at, f.created_at, "
    "COALESCE(u.nickname, '') AS nickname"
)


async def list_admin_feedback(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    status: int | None = None,
    category: str | None = None,
    keyword: str | None = None,
) -> AdminFeedbackPage:
    where = ["1 = 1"]
    params: dict[str, Any] = {
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    if status is not None:
        where.append("f.status = :status")
        params["status"] = status
    if category:
        where.append("f.category = :category")
        params["category"] = category
    if keyword:
        where.append("(f.content LIKE :kw OR u.nickname LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    clause = " AND ".join(where)
    total = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM user_feedback f "
                    "LEFT JOIN users u ON u.id = f.user_id "
                    f"WHERE {clause}"
                ),
                params,
            )
        ).scalar()
        or 0
    )
    rows = (
        await db.execute(
            text(
                f"SELECT {_ADMIN_COLUMNS} FROM user_feedback f "
                "LEFT JOIN users u ON u.id = f.user_id "
                f"WHERE {clause} ORDER BY f.id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()
    return AdminFeedbackPage(
        items=[_admin_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def get_admin_feedback(db: AsyncSession, feedback_id: int) -> AdminFeedbackItem:
    result = await db.execute(
        text(
            f"SELECT {_ADMIN_COLUMNS} FROM user_feedback f "
            "LEFT JOIN users u ON u.id = f.user_id WHERE f.id = :id"
        ),
        {"id": feedback_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    return _admin_item(row)


async def reply_feedback(
    db: AsyncSession, admin_id: int, feedback_id: int, reply_content: str
) -> AdminFeedbackItem:
    result = await db.execute(
        text("SELECT id FROM user_feedback WHERE id = :id FOR UPDATE"),
        {"id": feedback_id},
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="反馈不存在")
    await db.execute(
        text(
            "UPDATE user_feedback SET status = 2, reply_content = :reply, "
            "replied_by = :admin, replied_at = UTC_TIMESTAMP() WHERE id = :id"
        ),
        {"id": feedback_id, "reply": reply_content, "admin": admin_id},
    )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id) "
            "VALUES (:actor, 'support.feedback.reply', 'user_feedback', :id)"
        ),
        {"actor": admin_id, "id": feedback_id},
    )
    await db.commit()
    return await get_admin_feedback(db, feedback_id)
