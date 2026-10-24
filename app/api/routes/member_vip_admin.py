"""Member VIP and login history queries for the independent back office."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin, require_sensitive_operation,
)
from app.db.session import get_db
from app.schemas.member_vip_admin import AdminLoginLogItem, AdminLoginLogPage, AdminVipItem, AdminVipPage, AdminVipUpdate, AdminVipUpdateResponse, ImpersonateSessionResponse, LoginLogDeleteResult
from app.services.auth import create_impersonation_session
from app.services.member_vip_admin import clear_login_logs, delete_login_log, list_login_logs, update_vip
from app.services.sensitive_operations import abort_sensitive_operation, begin_sensitive_operation, finish_sensitive_operation

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


# ───── A12 平台用户登录日志（全局列表 / 单条删除 / 一键清空，数据源 user_login_log） ─────
# 静态段 /login-logs 先于 /{member_id} 系列注册，避免被 int 路径参数抢匹配。

@declare_permission("matchmaker.member.read")
@router.get("/login-logs", response_model=AdminLoginLogPage, summary="查询平台用户登录日志（A12）")
async def platform_login_logs(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=64, description="昵称/手机号/IP 模糊"),
    login_status: int | None = Query(None, ge=1, le=2, description="1 成功 2 失败"),
    login_type: int | None = Query(None, ge=1, le=3, description="1 微信 2 手机号 3 测试登录"),
    start_date: str | None = Query(None, max_length=10, description="登录时间起 YYYY-MM-DD（含）"),
    end_date: str | None = Query(None, max_length=10, description="登录时间止 YYYY-MM-DD（含）"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminLoginLogPage:
    current.require("matchmaker.member.read")
    scope, scope_params = _scope(current, _USER_CORRELATION)
    return await list_login_logs(db, page, page_size, search=search, login_status=login_status, login_type=login_type, start_date=start_date, end_date=end_date, scope=scope or None, scope_params=scope_params)


@declare_permission("matchmaker.member.manage")
@router.delete("/login-logs", response_model=LoginLogDeleteResult, summary="一键清空登录日志（幂等 + 二次确认）")
async def platform_login_logs_clear(
    search: str | None = Query(None, max_length=64),
    login_status: int | None = Query(None, ge=1, le=2),
    login_type: int | None = Query(None, ge=1, le=3),
    start_date: str | None = Query(None, max_length=10),
    end_date: str | None = Query(None, max_length=10),
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LoginLogDeleteResult:
    """A12：一键清空，需 confirm=true + Idempotency-Key。仅删当前筛选 + 数据范围内的日志。"""
    current.require("matchmaker.member.manage")
    scope, scope_params = _scope(current, _USER_CORRELATION)
    filters = {"search": search, "login_status": login_status, "login_type": login_type, "start_date": start_date, "end_date": end_date}
    reservation, replayed = await begin_sensitive_operation(db, actor_id=current.account.id, operation="member.login_log.clear", idempotency_key=idempotency_key, payload=filters)
    if replayed is not None:
        return LoginLogDeleteResult(**replayed)
    try:
        deleted = await clear_login_logs(db, current.account.id, scope=scope or None, scope_params=scope_params, **filters)
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    result = LoginLogDeleteResult(deleted=deleted)
    await finish_sensitive_operation(db, reservation, result.model_dump(mode="json"))
    return result


@declare_permission("matchmaker.member.manage")
@router.delete("/login-logs/{log_id}", response_model=LoginLogDeleteResult, summary="删除单条登录日志（幂等 + 二次确认）")
async def platform_login_log_delete(
    log_id: int = Path(..., ge=1),
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> LoginLogDeleteResult:
    """A12：删除单条登录日志，需 confirm=true + Idempotency-Key。越权/不存在返回 404。"""
    current.require("matchmaker.member.manage")
    scope, scope_params = _scope(current, _USER_CORRELATION)
    reservation, replayed = await begin_sensitive_operation(db, actor_id=current.account.id, operation="member.login_log.delete", idempotency_key=idempotency_key, payload={"log_id": log_id})
    if replayed is not None:
        return LoginLogDeleteResult(**replayed)
    try:
        deleted = await delete_login_log(db, current.account.id, log_id, scope=scope or None, scope_params=scope_params)
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    result = LoginLogDeleteResult(deleted=deleted)
    await finish_sensitive_operation(db, reservation, result.model_dump(mode="json"))
    return result


@declare_permission("matchmaker.member.impersonate")
@router.post("/{member_id}/impersonate", response_model=ImpersonateSessionResponse, status_code=202, summary="模拟登录（受限短时只读 token，幂等 + 二次确认）")
async def impersonate_member(
    member_id: int = Path(..., ge=1),
    request: Request = None,  # type: ignore[assignment]
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> ImpersonateSessionResponse:
    """A12-模拟登录：为目标会员签发 15 分钟只读会话，需 confirm=true + Idempotency-Key。

    只读：生成的 access token 带 imp 声明，只能执行安全方法，写操作被中间件 403。
    范围：只能模拟当前账号数据范围内的会员（D-16）；越权/不存在按 404。
    审计：user_session.impersonated_by + business_audit_log(admin.impersonate.create)。
    """
    current.require("matchmaker.member.impersonate")
    scope, scope_params = _scope(current, _MEMBER_CORRELATION)
    params: dict[str, object] = {"id": member_id, **scope_params}
    visible = await db.execute(text(f"SELECT 1 FROM users WHERE id = :id AND ({scope})"), params)
    if not visible.first():
        raise HTTPException(404, detail="会员不存在或无访问权限")
    client_ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    reservation, replayed = await begin_sensitive_operation(
        db,
        actor_id=current.account.id,
        operation="member.impersonate.create",
        idempotency_key=idempotency_key,
        payload={"member_id": member_id},
    )
    if replayed is not None:
        return ImpersonateSessionResponse(**replayed)
    try:
        result = await create_impersonation_session(db, current.account.id, member_id, client_ip, user_agent)
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    await finish_sensitive_operation(db, reservation, result)
    return ImpersonateSessionResponse(**result)


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
