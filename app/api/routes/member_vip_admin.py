"""Member VIP and login history queries for the independent back office."""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, get_current_matchmaker_admin
from app.db.session import get_db
from app.schemas.member_vip_admin import AdminLoginLogItem, AdminLoginLogPage, AdminVipItem, AdminVipPage, AdminVipUpdate, AdminVipUpdateResponse
from app.services.member_vip_admin import update_vip

router = APIRouter(prefix="/admin/members")

# 会员/订单/流水均无组织列，归属只存在于 resource_assignment，统一用 EXISTS 包装（D-16）。
_MEMBER_CORRELATION = "scope_assignment.user_id = users.id"
_USER_CORRELATION = "scope_assignment.user_id = u.id"

# 线上VIP 列表的表头排序白名单：值全部由服务端写死，不拼接用户输入。
_VIP_SORT_SQL = {
    # 默认：未过期在前，按到期日升序（快过期的先看）
    "expire_soon": "m.end_at IS NULL, m.end_at ASC, m.id DESC",
    "opened_at": "m.start_at DESC, m.id DESC",
    "expire_latest": "m.end_at IS NULL, m.end_at DESC, m.id DESC",
    "amount": "m.amount DESC, m.id DESC",
    "member": "u.id DESC",
}


def _scope(current: CurrentMatchmakerAdmin, correlation: str) -> tuple[str, dict[str, object]]:
    """生成四档数据范围谓词；唯一判定在 `CurrentMatchmakerAdmin.scope_clause`（D-16）。"""
    params: dict[str, object] = {}
    return current.scope_exists_clause(params, correlation=correlation), params


@router.patch("/{member_id}/vip", response_model=AdminVipUpdateResponse, summary="开通、续期或取消 VIP")
async def update_member_vip(member_id: int = Path(..., ge=1), body: AdminVipUpdate = ..., current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin), db: AsyncSession = Depends(get_db)) -> AdminVipUpdateResponse:
    current.require("matchmaker.member.manage")
    scope, scope_params = _scope(current, _MEMBER_CORRELATION)
    return await update_vip(db, current.account.id, member_id, body, scope=scope, scope_params=scope_params)


@router.get("/vip", response_model=AdminVipPage, summary="查询 VIP 会员")
async def vip_members(page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=100), expiring_within_days: int | None = Query(None, ge=1, le=3650), search: str | None = Query(None, max_length=64), vip_level: str | None = Query(None, max_length=64), open_method: str | None = Query(None, pattern="^(admin|self)$"), open_nature: str | None = Query(None, pattern="^(first|renew|upgrade|again)$"), vip_status: str | None = Query(None, pattern="^(active|expired)$"), sort_by: str | None = Query(None, pattern="^(expire_soon|opened_at|expire_latest|amount|member)$", description="表头排序：expire_soon 最快到期 / opened_at 开通时间 / expire_latest 最晚到期 / amount 支付金额 / member 会员ID"), current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin), db: AsyncSession = Depends(get_db)) -> AdminVipPage:
    current.require("matchmaker.member.read")
    where = ["m.status <> 3"]
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    scope, scope_params = _scope(current, _USER_CORRELATION)
    if scope:
        params.update(scope_params)
        where.append(f"({scope})")
    if search:
        where.append("(u.nickname LIKE CONCAT('%', :search, '%') OR u.phone LIKE CONCAT('%', :search, '%'))")
        params["search"] = search
    if vip_level:
        where.append("m.package_type = :vip_level")
        params["vip_level"] = vip_level
    if vip_status == "active":
        where.append("(m.end_at IS NULL OR m.end_at > UTC_TIMESTAMP())")
    if vip_status == "expired":
        where.append("m.end_at IS NOT NULL AND m.end_at <= UTC_TIMESTAMP()")
    if expiring_within_days is not None:
        where.append("m.end_at IS NOT NULL AND m.end_at <= DATE_ADD(UTC_TIMESTAMP(), INTERVAL :days DAY)")
        params["days"] = expiring_within_days
    clause = " AND ".join(where)
    base = "FROM user_membership m JOIN users u ON u.id = m.user_id"
    nature = "CASE WHEN (SELECT COUNT(*) FROM user_membership prev WHERE prev.user_id=m.user_id AND prev.id<m.id)>1 THEN 'again' WHEN (SELECT COUNT(*) FROM user_membership prev WHERE prev.user_id=m.user_id AND prev.id<m.id)=1 THEN 'renew' ELSE 'first' END"
    method = "CASE WHEN EXISTS (SELECT 1 FROM payment_order po WHERE po.order_no=m.order_no AND po.user_id=m.user_id AND po.status=1) THEN 'self' ELSE 'admin' END"
    if open_method:
        where.append(f"({method}) = :open_method")
        params["open_method"] = open_method
    if open_nature:
        where.append(f"({nature}) = :open_nature")
        params["open_nature"] = open_nature
    clause = " AND ".join(where)
    order = _VIP_SORT_SQL.get(str(sort_by), _VIP_SORT_SQL["expire_soon"])
    rows = await db.execute(text(f"SELECT m.id membership_id, m.user_id, u.nickname, u.phone, m.package_type, m.amount, m.order_no, m.start_at, m.end_at, m.status, {method} open_method, {nature} open_nature, 0 line_total, 0 line_remaining {base} WHERE {clause} ORDER BY {order} LIMIT :limit OFFSET :offset"), params)
    count = await db.execute(text(f"SELECT COUNT(*) {base} WHERE {clause}"), {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = int(count.scalar() or 0)
    return AdminVipPage(items=[AdminVipItem(**dict(row)) for row in rows.mappings().all()], page=page, page_size=page_size, total=total, has_more=page * page_size < total)


@router.get("/{member_id}/behavior/login-logs", response_model=AdminLoginLogPage, summary="查询会员登录日志")
async def login_logs(member_id: int = Path(..., ge=1), page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, ge=1, le=100), current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin), db: AsyncSession = Depends(get_db)) -> AdminLoginLogPage:
    current.require("matchmaker.member.read")
    base = "FROM user_login_log l JOIN users u ON u.id = l.user_id"
    params = {"user_id": member_id, "limit": page_size, "offset": (page - 1) * page_size}
    scope, scope_params = _scope(current, _USER_CORRELATION)
    scope_filter = ""
    if scope:
        params.update(scope_params)
        scope_filter = f" AND ({scope})"
    rows = await db.execute(text(f"SELECT l.id, l.user_id, u.nickname, l.login_status, l.ip, l.device_id, l.platform, l.failure_reason, l.created_at {base} WHERE l.user_id = :user_id{scope_filter} ORDER BY l.id DESC LIMIT :limit OFFSET :offset"), params)
    count = await db.execute(text(f"SELECT COUNT(*) {base} WHERE l.user_id = :user_id{scope_filter}"), {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = int(count.scalar() or 0)
    return AdminLoginLogPage(items=[AdminLoginLogItem(**dict(row)) for row in rows.mappings().all()], page=page, page_size=page_size, total=total, has_more=page * page_size < total)
