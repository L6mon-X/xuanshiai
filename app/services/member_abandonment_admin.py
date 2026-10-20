"""会员弃海（A9/B3）服务。

弃海口径：``member_abandonment`` 中 ``restored_at IS NULL`` 的有效记录即「在弃海池」。
会员归属本身不带列，统一由 ``resource_assignment`` 判定：查询时 JOIN ``users u``
后把路由层生成的 ``scope_exists_clause`` 谓词施加在 ``u.id`` 上（D-16 唯一实现）。

历史口径：客源侧 ``customer_lead.status='LOST'`` 的会员由迁移回填成
``abandon_type='lead_sync'`` 记录，因此列表/计数与历史数据连续。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.member_abandonment_admin import (
    AbandonedMemberItem,
    AbandonedMemberPage,
    MemberAbandonmentItem,
    MemberAbandonmentPage,
    MemberAbandonRequest,
    MemberRestoreRequest,
)

# 弃海会员行：与 matchmaker_crm_admin._member_query 的展示列保持同一口径，
# 只追加弃海维度字段；敏感联系方式沿用列表页的脱敏规则由上层决定（此处返回原值列，
# 与会员列表一致，列表页本身不做掩码）。
_ABANDONED_SELECT = """SELECT u.id, u.nickname, u.phone, u.gender, u.status, u.created_at,
    COALESCE(u.avatar, JSON_UNQUOTE(JSON_EXTRACT(p.photos, '$[0]'))) AS avatar,
    u.birthday, u.is_married, p.height, p.income, p.hometown, p.residence,
    p.constellation, p.zodiac, p.household, p.ethnicity, p.house, p.car, p.smoking,
    p.drinking, p.religion, p.marriage_plan,
    ua.education, ua.school, ua.job, ua.company,
    COALESCE(ua.auth_status, 0) AS auth_status, p.intention_level, f.last_follow_at, f.next_follow_at,
    v.vip_end_at, a.matchmaker_id, COALESCE(pr.match_status, 1) AS match_status,
    u.source, u.region, COALESCE(u.cert_status, 0) AS cert_status,
    COALESCE(u.wechat_added, 0) AS wechat_added, COALESCE(u.promoted, 0) AS promoted,
    COALESCE(u.newcomer, 0) AS newcomer, COALESCE(u.activity_signup, 0) AS activity_signup,
    u.level, u.fetched_at, a.assigned_at,
    CASE WHEN v.user_id IS NULL OR (v.vip_end_at IS NOT NULL AND v.vip_end_at <= UTC_TIMESTAMP())
        THEN 0 ELSE 1 END AS is_vip,
    ma.abandoned_at, ma.reason AS abandoned_reason, ma.abandon_type, ma.abandoned_by
    FROM member_abandonment ma
    JOIN users u ON u.id = ma.user_id
    LEFT JOIN user_profile p ON p.user_id = u.id
    LEFT JOIN user_auth ua ON ua.user_id = u.id
    LEFT JOIN user_privacy pr ON pr.user_id = u.id
    LEFT JOIN (SELECT user_id, MAX(end_at) AS vip_end_at FROM user_membership
        WHERE status = 1 GROUP BY user_id) v ON v.user_id = u.id
    LEFT JOIN (SELECT user_id, MAX(matchmaker_id) AS matchmaker_id, MAX(organization_id) AS organization_id,
        MAX(effective_at) AS assigned_at FROM resource_assignment WHERE status = 1
        GROUP BY user_id) a ON a.user_id = u.id
    LEFT JOIN (SELECT user_id, MAX(created_at) last_follow_at, MAX(next_follow_at) next_follow_at
        FROM member_follow_up GROUP BY user_id) f ON f.user_id = u.id"""

_ABANDONMENT_SELECT = """SELECT ab.id, ab.user_id, u.nickname, ab.reason, ab.abandon_type,
    ab.abandoned_by, ab.abandoned_at, ab.restored_by, ab.restored_at, ab.restore_reason,
    ab.assigned_matchmaker_id
    FROM member_abandonment ab JOIN users u ON u.id = ab.user_id"""


def _abandoned_item(row: Any) -> AbandonedMemberItem:
    return AbandonedMemberItem(**dict(row))


def _abandonment_item(row: Any) -> MemberAbandonmentItem:
    return MemberAbandonmentItem(**dict(row))


async def list_abandoned_members(
    db: AsyncSession,
    page: int,
    page_size: int,
    search: str | None,
    matchmaker_id: int | None,
    organization_id: int | None,
    abandon_type: str | None,
    start_date: str | None,
    end_date: str | None,
    *,
    scope: str,
    scope_params: dict[str, object],
) -> AbandonedMemberPage:
    where: list[str] = ["ma.restored_at IS NULL"]
    params: dict[str, Any] = dict(scope_params)
    if scope and scope != "1 = 1":
        where.append(f"({scope})")
    if search:
        where.append("(u.nickname LIKE :search OR u.phone LIKE :search)")
        params["search"] = f"%{search}%"
    if matchmaker_id is not None:
        where.append("a.matchmaker_id = :matchmaker_id")
        params["matchmaker_id"] = matchmaker_id
    if organization_id is not None:
        where.append("a.organization_id = :organization_id")
        params["organization_id"] = organization_id
    if abandon_type in {"manual", "lead_sync", "auto"}:
        where.append("ma.abandon_type = :abandon_type")
        params["abandon_type"] = abandon_type
    if start_date:
        where.append("ma.abandoned_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where.append("ma.abandoned_at < DATE_ADD(:end_date, INTERVAL 1 DAY)")
        params["end_date"] = end_date
    clause = " AND ".join(where)
    base = (
        "FROM member_abandonment ma JOIN users u ON u.id = ma.user_id"
        " LEFT JOIN (SELECT user_id, MAX(matchmaker_id) AS matchmaker_id,"
        " MAX(organization_id) AS organization_id, MAX(effective_at) AS assigned_at"
        " FROM resource_assignment WHERE status = 1 GROUP BY user_id) a ON a.user_id = u.id"
    )
    total = int(
        (await db.execute(text(f"SELECT COUNT(*) {base} WHERE {clause}"), params)).scalar() or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_ABANDONED_SELECT} WHERE {clause} ORDER BY ma.abandoned_at DESC, ma.id DESC"
                 " LIMIT :limit OFFSET :offset"),
            params,
        )
    ).mappings().all()
    return AbandonedMemberPage(
        items=[_abandoned_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def _ensure_member_in_scope(
    db: AsyncSession, member_id: int, scope: str, scope_params: dict[str, object]
) -> None:
    params = dict(scope_params)
    params["member_id"] = member_id
    predicate = f"({scope})" if scope and scope != "1 = 1" else "1 = 1"
    exists = (
        await db.execute(
            text(f"SELECT 1 FROM users u WHERE u.id = :member_id AND {predicate}"),
            params,
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(404, detail="会员不存在")


async def abandon_member(
    db: AsyncSession,
    actor_id: int,
    member_id: int,
    body: MemberAbandonRequest,
    *,
    scope: str,
    scope_params: dict[str, object],
) -> MemberAbandonmentItem:
    await _ensure_member_in_scope(db, member_id, scope, scope_params)
    active = (
        await db.execute(
            text(
                "SELECT id FROM member_abandonment WHERE user_id = :user_id AND restored_at IS NULL"
                " ORDER BY id DESC LIMIT 1"
            ),
            {"user_id": member_id},
        )
    ).scalar_one_or_none()
    if active:
        raise HTTPException(409, detail="该会员已在弃海池")
    result = await db.execute(
        text(
            "INSERT INTO member_abandonment (user_id, reason, abandon_type, abandoned_by)"
            " VALUES (:user_id, :reason, :abandon_type, :abandoned_by)"
        ),
        {
            "user_id": member_id,
            "reason": body.reason,
            "abandon_type": body.abandon_type,
            "abandoned_by": actor_id,
        },
    )
    abandonment_id = int(result.lastrowid)
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)"
            " VALUES (:actor, 'member.abandon', 'users', :id, :reason)"
        ),
        {"actor": actor_id, "id": member_id, "reason": body.reason[:255]},
    )
    await db.commit()
    row = (
        await db.execute(text(f"{_ABANDONMENT_SELECT} WHERE ab.id = :id"), {"id": abandonment_id})
    ).mappings().one()
    return _abandonment_item(row)


async def _ensure_service_matchmaker(db: AsyncSession, matchmaker_id: int) -> None:
    ok = (
        await db.execute(
            text(
                "SELECT 1 FROM users u WHERE u.id = :id AND u.status = 1"
                " AND EXISTS (SELECT 1 FROM user_role ur WHERE ur.user_id = u.id"
                " AND ur.role_code = 'service_matchmaker' AND ur.status = 1)"
            ),
            {"id": matchmaker_id},
        )
    ).scalar_one_or_none()
    if not ok:
        raise HTTPException(422, detail="只能分派给有效服务红娘")


async def restore_member(
    db: AsyncSession,
    actor_id: int,
    member_id: int,
    body: MemberRestoreRequest,
    *,
    scope: str,
    scope_params: dict[str, object],
) -> MemberAbandonmentItem:
    await _ensure_member_in_scope(db, member_id, scope, scope_params)
    active = (
        await db.execute(
            text(
                "SELECT id FROM member_abandonment WHERE user_id = :user_id AND restored_at IS NULL"
                " ORDER BY id DESC LIMIT 1"
            ),
            {"user_id": member_id},
        )
    ).scalar_one_or_none()
    if not active:
        raise HTTPException(409, detail="该会员不在弃海池")
    if body.matchmaker_id is not None:
        await _ensure_service_matchmaker(db, body.matchmaker_id)
    await db.execute(
        text(
            "UPDATE member_abandonment SET restored_by = :actor, restored_at = UTC_TIMESTAMP(),"
            " restore_reason = :reason, assigned_matchmaker_id = :matchmaker_id WHERE id = :id"
        ),
        {
            "actor": actor_id,
            "reason": body.reason,
            "matchmaker_id": body.matchmaker_id,
            "id": int(active),
        },
    )
    if body.matchmaker_id is not None:
        # 捞回即分派：沿用客源入库的归属写入口径（resource_assignment source/status）。
        await db.execute(
            text(
                "INSERT INTO resource_assignment"
                " (user_id, organization_id, matchmaker_id, source, status, assigned_by)"
                " VALUES (:user_id, NULL, :matchmaker_id, 'abandon_restore', 1, :assigned_by)"
            ),
            {"user_id": member_id, "matchmaker_id": body.matchmaker_id, "assigned_by": actor_id},
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)"
            " VALUES (:actor, 'member.restore', 'users', :id, :reason)"
        ),
        {"actor": actor_id, "id": member_id, "reason": body.reason[:255]},
    )
    await db.commit()
    row = (
        await db.execute(text(f"{_ABANDONMENT_SELECT} WHERE ab.id = :id"), {"id": int(active)})
    ).mappings().one()
    return _abandonment_item(row)


async def list_abandonments(
    db: AsyncSession,
    page: int,
    page_size: int,
    active_only: bool,
    abandon_type: str | None,
    search: str | None,
    *,
    scope: str,
    scope_params: dict[str, object],
) -> MemberAbandonmentPage:
    where: list[str] = []
    params: dict[str, Any] = dict(scope_params)
    if scope and scope != "1 = 1":
        where.append(f"({scope})")
    if active_only:
        where.append("ab.restored_at IS NULL")
    if abandon_type in {"manual", "lead_sync", "auto"}:
        where.append("ab.abandon_type = :abandon_type")
        params["abandon_type"] = abandon_type
    if search:
        where.append("(u.nickname LIKE :search OR u.phone LIKE :search)")
        params["search"] = f"%{search}%"
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    base = "FROM member_abandonment ab JOIN users u ON u.id = ab.user_id"
    total = int((await db.execute(text(f"SELECT COUNT(*) {base} {clause}"), params)).scalar() or 0)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_ABANDONMENT_SELECT} {clause} ORDER BY ab.id DESC LIMIT :limit OFFSET :offset"),
            params,
        )
    ).mappings().all()
    return MemberAbandonmentPage(
        items=[_abandonment_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )
