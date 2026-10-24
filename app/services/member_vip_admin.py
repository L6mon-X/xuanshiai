"""Audited VIP administration backed by paid membership orders."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.member_vip_admin import (
    AdminLoginLogItem, AdminLoginLogPage, AdminVipUpdate, AdminVipUpdateResponse,
)


async def update_vip(
    db: AsyncSession,
    admin_id: int,
    user_id: int,
    request: AdminVipUpdate,
    *,
    scope: str | None = None,
    scope_params: dict[str, object] | None = None,
) -> AdminVipUpdateResponse:
    """开通/续期/取消 VIP。

    ``scope`` 为路由层用 `CurrentMatchmakerAdmin.scope_exists_clause`（D-16）生成的
    四档谓词；会员不在数据范围内时按「会员不存在」返回 404（不泄露存在性），
    也保证越权写不落库。
    """
    where = ["id = :id"]
    params: dict[str, object] = {"id": user_id}
    if scope:
        params.update(scope_params or {})
        where.append(f"({scope})")
    user = await db.execute(text(f"SELECT id FROM users WHERE {' AND '.join(where)} FOR UPDATE"), params)
    if not user.scalar():
        raise HTTPException(404, detail="会员不存在")

    if request.action == "CANCEL":
        current = (await db.execute(text("""SELECT id, package_type, order_no, start_at, end_at FROM user_membership
            WHERE user_id = :user_id AND status = 1 AND (end_at IS NULL OR end_at > UTC_TIMESTAMP())
            ORDER BY end_at DESC, id DESC LIMIT 1 FOR UPDATE"""), {"user_id": user_id})).mappings().first()
        if not current:
            raise HTTPException(409, detail="会员当前没有有效 VIP")
        await db.execute(text("UPDATE user_membership SET status = 3, updated_at = UTC_TIMESTAMP() WHERE id = :id"), {"id": current["id"]})
        await db.execute(text("""INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)
            VALUES (:actor, 'member.vip.cancel', 'user_membership', :id, :reason)"""), {"actor": admin_id, "id": current["id"], "reason": request.reason})
        await db.commit()
        return AdminVipUpdateResponse(membership_id=int(current["id"]), user_id=user_id, action=request.action, package_type=current["package_type"], status=3, start_at=current["start_at"], end_at=current["end_at"], order_no=current["order_no"], reason=request.reason)

    order = (await db.execute(text("""SELECT po.id, po.order_no, po.amount, po.status, cp.code, cp.duration_days
        FROM payment_order po JOIN config_membership_package cp ON cp.code = :package_type
        WHERE po.order_no = :order_no AND po.user_id = :user_id AND po.type = 1 AND po.status = 1
        FOR UPDATE"""), {"package_type": request.package_type, "order_no": request.order_no, "user_id": user_id})).mappings().first()
    if not order:
        raise HTTPException(409, detail="必须提供该会员已支付且匹配套餐的会员订单")
    used = await db.execute(text("SELECT id FROM user_membership WHERE order_no = :order_no LIMIT 1 FOR UPDATE"), {"order_no": request.order_no})
    existing = used.scalar()
    if existing:
        row = (await db.execute(text("SELECT id, user_id, package_type, status, start_at, end_at, order_no FROM user_membership WHERE id = :id"), {"id": existing})).mappings().one()
        return AdminVipUpdateResponse(membership_id=int(row["id"]), user_id=int(row["user_id"]), action=request.action, package_type=row["package_type"], status=int(row["status"]), start_at=row["start_at"], end_at=row["end_at"], order_no=row["order_no"], reason="订单已处理")

    active = (await db.execute(text("""SELECT id, end_at FROM user_membership WHERE user_id = :user_id AND status = 1
        AND (end_at IS NULL OR end_at > UTC_TIMESTAMP()) ORDER BY end_at DESC, id DESC LIMIT 1 FOR UPDATE"""), {"user_id": user_id})).mappings().first()
    now = datetime.now(UTC).replace(tzinfo=None)
    start_at = active["end_at"] if request.action == "RENEW" and active and active["end_at"] else now
    end_at = start_at + timedelta(days=int(order["duration_days"]))
    result = await db.execute(text("""INSERT INTO user_membership (user_id, package_type, amount, order_no, start_at, end_at, status)
        VALUES (:user_id, :package_type, :amount, :order_no, :start_at, :end_at, 1)"""), {"user_id": user_id, "package_type": request.package_type, "amount": order["amount"], "order_no": request.order_no, "start_at": start_at, "end_at": end_at})
    membership_id = int(result.lastrowid)
    await db.execute(text("""INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)
        VALUES (:actor, :action, 'user_membership', :id, :reason)"""), {"actor": admin_id, "action": f"member.vip.{request.action.lower()}", "id": membership_id, "reason": request.reason or "已支付订单后台处理"})
    await db.commit()
    return AdminVipUpdateResponse(membership_id=membership_id, user_id=user_id, action=request.action, package_type=request.package_type, status=1, start_at=start_at, end_at=end_at, order_no=request.order_no, reason=request.reason)


# ───────────── A12 平台用户登录日志（全局列表 / 删除 / 清空，复用 user_login_log） ─────────────

def _login_log_filters(
    where: list[str], params: dict[str, object], *, search: str | None, login_status: int | None,
    login_type: int | None, start_date: str | None, end_date: str | None,
) -> None:
    """登录日志列表与「一键清空」共用的筛选谓词，保证清空口径与列表一致。"""
    if search:
        where.append("(u.nickname LIKE CONCAT('%', :search, '%') OR u.phone LIKE CONCAT('%', :search, '%') OR l.ip LIKE CONCAT('%', :search, '%'))")
        params["search"] = search
    if login_status is not None:
        where.append("l.login_status = :login_status")
        params["login_status"] = login_status
    if login_type is not None:
        where.append("l.login_type = :login_type")
        params["login_type"] = login_type
    if start_date:
        where.append("l.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where.append("l.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)")
        params["end_date"] = end_date


async def list_login_logs(
    db: AsyncSession, page: int, page_size: int, *, search: str | None = None,
    login_status: int | None = None, login_type: int | None = None,
    start_date: str | None = None, end_date: str | None = None,
    scope: str | None = None, scope_params: dict[str, object] | None = None,
) -> AdminLoginLogPage:
    """平台用户登录日志全局列表（A12）。按 D-16 作用域收口，倒序分页。"""
    where = ["1 = 1"]
    params: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    base = "FROM user_login_log l JOIN users u ON u.id = l.user_id"
    if scope:
        params.update(scope_params or {})
        where.append(f"({scope})")
    _login_log_filters(where, params, search=search, login_status=login_status, login_type=login_type, start_date=start_date, end_date=end_date)
    clause = " AND ".join(where)
    rows = await db.execute(text(f"""SELECT l.id, l.user_id, u.nickname, u.phone, l.login_type, l.login_status, l.ip,
        l.device_id, l.platform, l.failure_reason, l.created_at {base} WHERE {clause} ORDER BY l.id DESC LIMIT :limit OFFSET :offset"""), params)
    count = await db.execute(text(f"SELECT COUNT(*) {base} WHERE {clause}"), {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = int(count.scalar() or 0)
    return AdminLoginLogPage(items=[AdminLoginLogItem(**dict(row)) for row in rows.mappings().all()], page=page, page_size=page_size, total=total, has_more=page * page_size < total)


async def delete_login_log(
    db: AsyncSession, admin_id: int, log_id: int, *, scope: str | None = None, scope_params: dict[str, object] | None = None,
) -> int:
    """删除单条平台用户登录日志（A12）。越权/不存在返回 404，不泄露存在性。"""
    where = ["l.id = :id"]
    params: dict[str, object] = {"id": log_id}
    if scope:
        params.update(scope_params or {})
        where.append(f"({scope})")
    res = await db.execute(text(f"""DELETE l FROM user_login_log l JOIN users u ON u.id = l.user_id
        WHERE {' AND '.join(where)}"""), params)
    deleted = int(res.rowcount or 0)
    if not deleted:
        raise HTTPException(404, detail="登录日志不存在或不在数据范围内")
    await db.execute(text("""INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)
        VALUES (:actor, 'member.login_log.delete', 'user_login_log', :id, :reason)"""), {"actor": admin_id, "id": log_id, "reason": "后台删除登录日志"})
    await db.commit()
    return deleted


async def clear_login_logs(
    db: AsyncSession, admin_id: int, *, search: str | None = None, login_status: int | None = None,
    login_type: int | None = None, start_date: str | None = None, end_date: str | None = None,
    scope: str | None = None, scope_params: dict[str, object] | None = None,
) -> int:
    """一键清空登录日志（A12）：按当前筛选 + 数据范围删除，返回删除行数。"""
    where = ["1 = 1"]
    params: dict[str, object] = {}
    if scope:
        params.update(scope_params or {})
        where.append(f"({scope})")
    _login_log_filters(where, params, search=search, login_status=login_status, login_type=login_type, start_date=start_date, end_date=end_date)
    clause = " AND ".join(where)
    res = await db.execute(text(f"""DELETE l FROM user_login_log l JOIN users u ON u.id = l.user_id WHERE {clause}"""), params)
    deleted = int(res.rowcount or 0)
    await db.execute(text("""INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id, reason)
        VALUES (:actor, 'member.login_log.clear', 'user_login_log', NULL, :reason)"""), {"actor": admin_id, "reason": f"后台清空登录日志 {deleted} 条"})
    await db.commit()
    return deleted

