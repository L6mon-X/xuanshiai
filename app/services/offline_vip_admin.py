"""线下VIP会员服务：列表 / 统计 / 新增 / 编辑 / 详情 / 成功约见修改记录。

对应前端页面：会员CRM → 线下VIP（/love-user-vip-underline）。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.offline_vip_admin import (
    CONTRACT_STATUS_LABELS,
    PROGRESS_LABELS,
    OfflineVipCreate,
    OfflineVipItem,
    OfflineVipMeetLogItem,
    OfflineVipMeetLogPage,
    OfflineVipOption,
    OfflineVipOptions,
    OfflineVipPage,
    OfflineVipStatistics,
    OfflineVipUpdate,
)

# 列表公共投影：会员 + 三名红娘 + 最近跟进时间
_SELECT_BODY = """
SELECT v.id, v.user_id, u.nickname, u.avatar, u.phone,
       v.sign_date, v.package_name, v.progress, v.service_start, v.service_end,
       v.contract_amount, v.contract_status, v.contract_no,
       v.promise_meet_count, v.success_meet_count, v.remark, v.attach_urls,
       v.created_at, v.updated_at,
       v.sales_matchmaker_id, su.nickname AS sales_matchmaker_name,
       v.service_matchmaker_id, cu.nickname AS service_matchmaker_name,
       v.promoter_id, pu.nickname AS promoter_name,
       (SELECT MAX(f.created_at) FROM member_follow_up f WHERE f.user_id = v.user_id) AS last_follow_at
FROM offline_vip v
JOIN users u ON u.id = v.user_id
LEFT JOIN users su ON su.id = v.sales_matchmaker_id
LEFT JOIN users cu ON cu.id = v.service_matchmaker_id
LEFT JOIN users pu ON pu.id = v.promoter_id
"""

# 计数用（不需要展示列，避免多算 join）
_COUNT_BODY = "FROM offline_vip v JOIN users u ON u.id = v.user_id"

# 筛选关键字匹配的会员实名来源
_KEYWORD_SQL = (
    "(u.nickname LIKE CONCAT('%', :keyword, '%')"
    " OR u.phone LIKE CONCAT('%', :keyword, '%')"
    " OR CONCAT('G', LPAD(u.id, 6, '0')) LIKE CONCAT('%', :keyword, '%')"
    " OR EXISTS (SELECT 1 FROM user_auth au WHERE au.user_id = u.id"
    "            AND au.real_name LIKE CONCAT('%', :keyword, '%')))"
)

# 套餐类型默认兜底选项（库中尚无历史套餐时展示）
_DEFAULT_PACKAGES = ["基础服务套餐", "标准服务套餐", "尊享服务套餐", "私人定制套餐"]


def _apply_scope(
    where: list[str],
    params: dict[str, Any],
    scope: str | None,
    scope_params: dict[str, Any] | None,
) -> None:
    """把四档数据范围谓词并入查询（D-16）。

    `offline_vip` 无组织列，归属按会员（`v.user_id`）的 ``resource_assignment``
    判定（与会员 CRM / 会员跟进一致）；谓词由路由层用
    `CurrentMatchmakerAdmin.scope_exists_clause`（唯一实现）生成后下传。
    """
    if not scope:
        return
    params.update(scope_params or {})
    where.append(f"({scope})")


def _int(value: Any) -> int:
    return int(value or 0)


def _money(value: Any) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01"))


def _progress_label(progress: str | None) -> str:
    return PROGRESS_LABELS.get(str(progress or "matching"), "匹配推荐中")


def _contract_label(status: str | None) -> str:
    return CONTRACT_STATUS_LABELS.get(str(status or "none"), "未发起")


def _attach_urls(value: Any) -> list[str]:
    """attach_urls 为 JSON 列：驱动可能返回 list，也可能返回 str。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item]
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except ValueError:
            return [stripped]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        return [str(parsed)]
    return []


def _row(payload: dict[str, Any]) -> OfflineVipItem:
    progress = str(payload.get("progress") or "matching")
    contract_status = str(payload.get("contract_status") or "none")
    return OfflineVipItem(
        id=int(payload["id"]),
        user_id=int(payload["user_id"]),
        member_code=f"G{int(payload['user_id']):06d}",
        nickname=payload.get("nickname"),
        avatar=payload.get("avatar"),
        phone=payload.get("phone"),
        sign_date=payload.get("sign_date"),
        package_name=payload.get("package_name"),
        progress=progress,
        progress_label=_progress_label(progress),
        service_start=payload.get("service_start"),
        service_end=payload.get("service_end"),
        last_follow_at=payload.get("last_follow_at"),
        contract_amount=_money(payload.get("contract_amount")),
        sales_matchmaker_id=payload.get("sales_matchmaker_id"),
        sales_matchmaker_name=payload.get("sales_matchmaker_name"),
        service_matchmaker_id=payload.get("service_matchmaker_id"),
        service_matchmaker_name=payload.get("service_matchmaker_name"),
        promoter_id=payload.get("promoter_id"),
        promoter_name=payload.get("promoter_name"),
        contract_status=contract_status,
        contract_status_label=_contract_label(contract_status),
        contract_no=payload.get("contract_no"),
        promise_meet_count=_int(payload.get("promise_meet_count")),
        success_meet_count=_int(payload.get("success_meet_count")),
        remark=payload.get("remark"),
        attach_urls=_attach_urls(payload.get("attach_urls")),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


# 服务状态：`progress` 是服务进度，service_status 是「服务期是否仍在」的独立维度。
# 库中无退费字段，「无退费风险」按「仍在服务期且已履约约见数达到承诺数」判定
# （承诺数为 0 视为无风险），判定口径写在 docs/api/offline-vip.md。
_SERVICE_STATUS_SQL = {
    "active": "v.service_end IS NOT NULL AND v.service_end >= CURDATE()",
    "expired": "v.service_end IS NOT NULL AND v.service_end < CURDATE()",
    "no_refund_risk": (
        "v.service_end IS NOT NULL AND v.service_end >= CURDATE()"
        " AND v.success_meet_count >= v.promise_meet_count"
    ),
}

# 统计/排序维度：`member_last_paid` 与 `member_history_paid` 按会员维度聚合，
# `monthly_sales` / `yearly_sales` / `monthly_champion` 按销售红娘维度聚合销售额。
_SORT_BY_SQL = {
    "member_last_paid": "COALESCE((SELECT MAX(po.pay_time) FROM payment_order po WHERE po.user_id = v.user_id AND po.status = 1), '1970-01-01') DESC, v.id DESC",
    "member_history_paid": "COALESCE((SELECT SUM(po.amount) FROM payment_order po WHERE po.user_id = v.user_id AND po.status = 1), 0) DESC, v.id DESC",
    "monthly_sales": "COALESCE(_month.amount, 0) DESC, v.id DESC",
    "yearly_sales": "COALESCE(_year.amount, 0) DESC, v.id DESC",
    "monthly_champion": "COALESCE(_month.amount, 0) DESC, COALESCE(_year.amount, 0) DESC, v.id DESC",
}

# 表头列排序白名单（与上面的统计维度 sort_by 是两回事）：
# 值全部由服务端写死，不拼接用户输入。
COLUMN_SORT_SQL = {
    "sign_date": "v.sign_date DESC, v.id DESC",
    "package": "v.package_name ASC, v.id DESC",
    "progress": "v.progress ASC, v.id DESC",
    # last_follow_at 是 SELECT 里的子查询别名，MySQL 不允许在 ORDER BY 里引用，
    # 这里把同一个子查询再写一遍。
    "last_follow": "COALESCE((SELECT MAX(f.created_at) FROM member_follow_up f WHERE f.user_id = v.user_id), '1970-01-01') DESC, v.id DESC",
    "amount": "v.contract_amount DESC, v.id DESC",
    "matchmaker": "v.service_matchmaker_id ASC, v.id DESC",
    "id": "v.id DESC",
}

# 销售额排序要额外左连接当月/当年已支付订单汇总，未选这些维度时不附加 join。
_SALES_JOIN = """
LEFT JOIN (SELECT v2.sales_matchmaker_id AS matchmaker_id, SUM(po.amount) AS amount
           FROM offline_vip v2 JOIN payment_order po
             ON po.user_id = v2.user_id AND po.status = 1
           WHERE v2.deleted_at IS NULL AND v2.sales_matchmaker_id IS NOT NULL
             AND po.pay_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
           GROUP BY v2.sales_matchmaker_id) _month
  ON _month.matchmaker_id = v.sales_matchmaker_id
LEFT JOIN (SELECT v3.sales_matchmaker_id AS matchmaker_id, SUM(po.amount) AS amount
           FROM offline_vip v3 JOIN payment_order po
             ON po.user_id = v3.user_id AND po.status = 1
           WHERE v3.deleted_at IS NULL AND v3.sales_matchmaker_id IS NOT NULL
             AND po.pay_time >= MAKEDATE(YEAR(CURDATE()), 1)
           GROUP BY v3.sales_matchmaker_id) _year
  ON _year.matchmaker_id = v.sales_matchmaker_id
"""


async def list_vips(
    db: AsyncSession,
    page: int,
    page_size: int,
    progress: str | None = None,
    sales_matchmaker_id: int | None = None,
    service_matchmaker_id: int | None = None,
    promoter_id: int | None = None,
    sign_start: str | None = None,
    sign_end: str | None = None,
    keyword: str | None = None,
    service_status: str | None = None,
    sort_by: str | None = None,
    column_sort: str | None = None,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipPage:
    """线下VIP 分页列表。progress 为空表示「全部」。"""
    conditions = ["v.deleted_at IS NULL"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    _apply_scope(conditions, params, scope, scope_params)
    if progress:
        conditions.append("v.progress = :progress")
        params["progress"] = progress
    if sales_matchmaker_id:
        conditions.append("v.sales_matchmaker_id = :sales_matchmaker_id")
        params["sales_matchmaker_id"] = sales_matchmaker_id
    if service_matchmaker_id:
        conditions.append("v.service_matchmaker_id = :service_matchmaker_id")
        params["service_matchmaker_id"] = service_matchmaker_id
    if promoter_id:
        conditions.append("v.promoter_id = :promoter_id")
        params["promoter_id"] = promoter_id
    if sign_start:
        conditions.append("v.sign_date >= :sign_start")
        params["sign_start"] = sign_start
    if sign_end:
        conditions.append("v.sign_date <= :sign_end")
        params["sign_end"] = sign_end
    if keyword:
        conditions.append(_KEYWORD_SQL)
        params["keyword"] = keyword
    if service_status in _SERVICE_STATUS_SQL:
        conditions.append(_SERVICE_STATUS_SQL[service_status])
    where = " AND ".join(conditions)
    # 销售额维度需要带汇总 join；其余排序不附加 join，避免改变既有查询计划。
    join = _SALES_JOIN if sort_by in ("monthly_sales", "yearly_sales", "monthly_champion") else ""
    order_by = _SORT_BY_SQL.get(sort_by or "", "v.id DESC")
    # 表头点击排序优先：它更贴近用户的即时意图，未点表头时沿用原统计维度排序。
    if column_sort in COLUMN_SORT_SQL:
        order_by = COLUMN_SORT_SQL[column_sort]
    rows = await db.execute(
        text(f"{_SELECT_BODY}{join} WHERE {where} ORDER BY {order_by} LIMIT :limit OFFSET :offset"),
        params,
    )
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total = _int(
        (await db.scalar(text(f"SELECT COUNT(*) {_COUNT_BODY}{join} WHERE {where}"), count_params))
    )
    return OfflineVipPage(
        items=[_row(dict(row)) for row in rows.mappings().all()],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def statistics(
    db: AsyncSession,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipStatistics:
    """线下VIP 顶部 10 张统计卡。

    口径（详见 docs/api/offline-vip.md）：
    - 服务中：未过期且进度不属于「恋爱分手/已经领证」；
    - 即将到期：service_end 落在今天起 30 天内；
    - 已退费：offline_vip 无退费字段，无数据源，恒为 0。
    """
    where = ["v.deleted_at IS NULL"]
    params: dict[str, Any] = {}
    _apply_scope(where, params, scope, scope_params)
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) AS vip_count,
                    COALESCE(SUM(v.service_end IS NOT NULL AND v.service_end >= CURDATE()
                        AND v.progress NOT IN ('breakup','married')), 0) AS serving_count,
                    COALESCE(SUM(v.service_end IS NOT NULL
                        AND v.service_end >= CURDATE()
                        AND v.service_end <= DATE_ADD(CURDATE(), INTERVAL 30 DAY)), 0) AS expiring_count,
                    COALESCE(SUM(v.service_end IS NOT NULL AND v.service_end < CURDATE()), 0) AS expired_count,
                    COALESCE(SUM(v.contract_amount > 0), 0) AS paid_count,
                    COALESCE(SUM(v.promise_meet_count), 0) AS promise_meet_total,
                    COALESCE(SUM(CASE WHEN DATE_FORMAT(v.created_at, '%Y-%m')
                        = DATE_FORMAT(CURDATE(), '%Y-%m') THEN v.promise_meet_count ELSE 0 END), 0)
                        AS promise_meet_month,
                    COALESCE(SUM(v.progress IN ('paused','breakup')), 0) AS refund_risk_count
                FROM offline_vip v
                WHERE {' AND '.join(where)}
                """
            ),
            params,
        )
    ).mappings().one()
    store_count = _int(
        await db.scalar(
            text("SELECT COUNT(*) FROM organization WHERE org_type = 'store' AND status = 1")
        )
    )
    return OfflineVipStatistics(
        store_count=store_count,
        vip_count=_int(row["vip_count"]),
        serving_count=_int(row["serving_count"]),
        expiring_count=_int(row["expiring_count"]),
        expired_count=_int(row["expired_count"]),
        paid_count=_int(row["paid_count"]),
        promise_meet_total=_int(row["promise_meet_total"]),
        promise_meet_month=_int(row["promise_meet_month"]),
        refund_risk_count=_int(row["refund_risk_count"]),
        # offline_vip 无退费字段，无数据源
        refunded_count=0,
    )


async def options(
    db: AsyncSession,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipOptions:
    """筛选/抽屉下拉选项：服务红娘、销售红娘、推广红娘、套餐类型。

    「套餐类型」取自本账号可见的线下VIP记录（带作用域，D-16）；红娘为全局
    配置型字典，不随数据范围收敛。
    """
    staff_rows = (
        await db.execute(
            text(
                "SELECT u.id, u.nickname, p.role_tag FROM users u"
                " JOIN matchmaker_profile p ON p.user_id = u.id"
                " WHERE p.deleted_at IS NULL AND u.status = 1"
                " ORDER BY p.sort DESC, u.id ASC"
            )
        )
    ).mappings().all()
    staff = [
        OfflineVipOption(
            id=int(row["id"]),
            name=str(row["nickname"] or f"红娘#{int(row['id'])}"),
            extra="超级红娘" if str(row.get("role_tag") or "") == "super" else "普通红娘",
        )
        for row in staff_rows
    ]
    promoter_rows = (
        await db.execute(
            text(
                "SELECT u.id, COALESCE(a.real_name, u.nickname) AS name FROM users u"
                " JOIN user_matchmaker_apply a ON a.user_id = u.id"
                "   AND a.application_type = 'promoter'"
                " WHERE a.status = 1 ORDER BY u.id DESC"
            )
        )
    ).mappings().all()
    promoters = [
        OfflineVipOption(id=int(row["id"]), name=str(row["name"] or f"推广红娘#{int(row['id'])}"))
        for row in promoter_rows
    ]
    package_where = ["package_name IS NOT NULL", "package_name <> ''", "deleted_at IS NULL"]
    package_params: dict[str, Any] = {}
    _apply_scope(package_where, package_params, scope, scope_params)
    package_rows = (
        await db.execute(
            text(
                "SELECT DISTINCT package_name FROM offline_vip v"
                f" WHERE {' AND '.join(package_where)}"
                " ORDER BY package_name"
            ),
            package_params,
        )
    ).scalars().all()
    packages = [str(item) for item in package_rows if item]
    for fallback in _DEFAULT_PACKAGES:
        if fallback not in packages:
            packages.append(fallback)
    return OfflineVipOptions(
        sales_matchmakers=staff, service_matchmakers=staff, promoters=promoters, packages=packages
    )


async def _resolve_member(
    db: AsyncSession,
    body: OfflineVipCreate,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> int:
    """解析「会员账号」：优先 user_id，其次按 lookup 模糊搜索（昵称/手机/姓名/编号）。

    两种入口都带数据范围：越权会员按「不存在」返回 404（D-16）。
    """
    if body.user_id:
        where = ["u.id = :id", "u.status = 1"]
        params: dict[str, Any] = {"id": body.user_id}
        _apply_scope(where, params, scope, scope_params)
        found = await db.scalar(
            text(f"SELECT u.id FROM users u WHERE {' AND '.join(where)}"), params
        )
        if not found:
            raise HTTPException(404, detail="会员不存在或已停用")
        return int(found)
    if body.lookup:
        keyword = body.lookup.strip()
        column = "u.phone" if body.lookup_by == "phone" else "u.nickname"
        if body.lookup_by == "nickname":
            # 昵称/姓名/编号都按包含匹配
            condition = (
                "(u.nickname LIKE CONCAT('%', :keyword, '%')"
                " OR CONCAT('G', LPAD(u.id, 6, '0')) LIKE CONCAT('%', :keyword, '%')"
                " OR EXISTS (SELECT 1 FROM user_auth au WHERE au.user_id = u.id"
                "            AND au.real_name LIKE CONCAT('%', :keyword, '%')))"
            )
        else:
            condition = f"{column} = :keyword"
        lookup_where = ["u.status = 1", condition]
        lookup_params: dict[str, Any] = {"keyword": keyword}
        _apply_scope(lookup_where, lookup_params, scope, scope_params)
        found = await db.scalar(
            text(f"SELECT u.id FROM users u WHERE {' AND '.join(lookup_where)} ORDER BY u.id DESC LIMIT 1"),
            lookup_params,
        )
        if not found:
            raise HTTPException(404, detail="未找到匹配的会员，请核对昵称/手机/姓名/编号")
        return int(found)
    raise HTTPException(400, detail="请填写会员账号（昵称/手机/姓名/编号）")


async def create_vip(
    db: AsyncSession,
    account_id: int,
    body: OfflineVipCreate,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipItem:
    """新增线下VIP记录。"""
    user_id = await _resolve_member(db, body, scope, scope_params)
    duplicate = await db.scalar(
        text("SELECT id FROM offline_vip WHERE user_id = :uid AND deleted_at IS NULL LIMIT 1"),
        {"uid": user_id},
    )
    if duplicate:
        raise HTTPException(409, detail="该会员已存在线下VIP记录，请直接编辑")
    result = await db.execute(
        text(
            "INSERT INTO offline_vip (user_id, sales_matchmaker_id, service_matchmaker_id, promoter_id,"
            " sign_date, service_start, service_end, package_name, contract_amount,"
            " promise_meet_count, success_meet_count, remark, attach_urls, created_by)"
            " VALUES (:user_id, :sales_matchmaker_id, :service_matchmaker_id, :promoter_id,"
            " :sign_date, :service_start, :service_end, :package_name, :contract_amount,"
            " :promise_meet_count, :success_meet_count, :remark, :attach_urls, :created_by)"
        ),
        {
            "user_id": user_id,
            "sales_matchmaker_id": body.sales_matchmaker_id,
            "service_matchmaker_id": body.service_matchmaker_id,
            "promoter_id": body.promoter_id,
            "sign_date": body.sign_date,
            "service_start": body.service_start,
            "service_end": body.service_end,
            "package_name": body.package_name,
            "contract_amount": str(body.contract_amount),
            "promise_meet_count": body.promise_meet_count,
            "success_meet_count": body.success_meet_count,
            "remark": body.remark,
            "attach_urls": json.dumps(body.attach_urls, ensure_ascii=False),
            "created_by": account_id,
        },
    )
    vip_id = int(result.lastrowid)
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id)"
            " VALUES (:actor, 'offline_vip.create', 'offline_vip', :id)"
        ),
        {"actor": account_id, "id": vip_id},
    )
    await db.commit()
    return await get_vip(db, vip_id, scope=scope, scope_params=scope_params)


async def _fetch_row(
    db: AsyncSession,
    vip_id: int,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    where = ["v.id = :id", "v.deleted_at IS NULL"]
    params: dict[str, Any] = {"id": vip_id}
    _apply_scope(where, params, scope, scope_params)
    row = (
        await db.execute(
            text(f"{_SELECT_BODY} WHERE {' AND '.join(where)}"), params
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="线下VIP记录不存在")
    return dict(row)


async def get_vip(
    db: AsyncSession,
    vip_id: int,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipItem:
    return _row(await _fetch_row(db, vip_id, scope, scope_params))


async def update_vip(
    db: AsyncSession,
    vip_id: int,
    account_id: int,
    body: OfflineVipUpdate,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipItem:
    """编辑线下VIP；success_meet_count 发生变化时写入人工修改记录。"""
    current = await _fetch_row(db, vip_id, scope, scope_params)
    payload = body.model_dump(exclude_unset=True)
    payload.pop("meet_change_remark", None)

    assignments: list[str] = []
    params: dict[str, Any] = {"id": vip_id}
    for field, value in payload.items():
        if field == "attach_urls":
            value = json.dumps(value or [], ensure_ascii=False)
        elif isinstance(value, Decimal):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        assignments.append(f"{field} = :{field}")
        params[field] = value

    meet_record = None
    if body.success_meet_count is not None:
        before = _int(current.get("success_meet_count"))
        if body.success_meet_count != before:
            meet_record = (before, body.success_meet_count, body.meet_change_remark)

    if assignments:
        # 写路径同样带作用域谓词（D-16）：读校验与写之间若归属变化，UPDATE 也不越权落库。
        update_where = ["id = :id", "deleted_at IS NULL"]
        _apply_scope(update_where, params, scope, scope_params)
        await db.execute(
            text(f"UPDATE offline_vip SET {', '.join(assignments)} WHERE {' AND '.join(update_where)}"),
            params,
        )
    if meet_record is not None:
        before, after, remark = meet_record
        await db.execute(
            text(
                "INSERT INTO offline_vip_meet_log (vip_id, before_count, after_count, remark, changed_by)"
                " VALUES (:vip_id, :before_count, :after_count, :remark, :changed_by)"
            ),
            {
                "vip_id": vip_id,
                "before_count": before,
                "after_count": after,
                "remark": remark,
                "changed_by": account_id,
            },
        )
    await db.execute(
        text(
            "INSERT INTO business_audit_log (actor_user_id, action, resource_type, resource_id)"
            " VALUES (:actor, 'offline_vip.update', 'offline_vip', :id)"
        ),
        {"actor": account_id, "id": vip_id},
    )
    await db.commit()
    return await get_vip(db, vip_id, scope=scope, scope_params=scope_params)


async def list_meet_logs(
    db: AsyncSession,
    vip_id: int,
    page: int,
    page_size: int,
    *,
    scope: str | None = None,
    scope_params: dict[str, Any] | None = None,
) -> OfflineVipMeetLogPage:
    """成功约见次数人工修改记录分页。"""
    await _fetch_row(db, vip_id, scope, scope_params)
    rows = await db.execute(
        text(
            "SELECT l.id, l.vip_id, l.before_count, l.after_count, l.remark,"
            " l.changed_by, l.created_at, COALESCE(acc.display_name, u.nickname) AS changed_by_name"
            " FROM offline_vip_meet_log l"
            " LEFT JOIN matchmaker_admin_account acc ON acc.id = l.changed_by"
            " LEFT JOIN users u ON u.id = l.changed_by"
            " WHERE l.vip_id = :vip_id ORDER BY l.id DESC LIMIT :limit OFFSET :offset"
        ),
        {"vip_id": vip_id, "limit": page_size, "offset": (page - 1) * page_size},
    )
    total = _int(
        await db.scalar(
            text("SELECT COUNT(*) FROM offline_vip_meet_log WHERE vip_id = :vip_id"),
            {"vip_id": vip_id},
        )
    )
    return OfflineVipMeetLogPage(
        items=[
            OfflineVipMeetLogItem(
                id=int(row["id"]),
                vip_id=int(row["vip_id"]),
                before_count=_int(row["before_count"]),
                after_count=_int(row["after_count"]),
                remark=row["remark"],
                changed_by=row["changed_by"],
                changed_by_name=row["changed_by_name"] or "admin",
                created_at=row["created_at"],
            )
            for row in rows.mappings().all()
        ],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )
