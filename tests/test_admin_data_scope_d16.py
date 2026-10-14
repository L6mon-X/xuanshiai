"""D-16 回归：后台数据范围收口补齐（客源/推广订单/合伙人/商家联盟/会员VIP/线下VIP/会员跟进）。

背景（见 `docs/全项目后端详细修改方案清单-2026-10-12.md` D-16）：上述模块的路由层虽已
注入 `CurrentMatchmakerAdmin`，但作用域谓词**没有下传服务层**，导致 STORE / ORGANIZATION /
SELF 账号能读到范围外数据。本文件冻结收口后的行为：

1. 每个模块的路由层都必须调用 `scope_exists_clause`（唯一四档实现），
   且不得在路由层重新分支 `data_scope` / `org_type` / `parent_id`；
2. 范围外读取统一返回 404（不泄露存在性），范围外写操作不得提交；
3. 未绑定组织/红娘的账号必须 fail-closed（`1 = 0`），绝不退化为 `1 = 1`。

真实多组织账号的端到端越权验证需要隔离 MySQL，留 TODO（见文末）。
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.api.dependencies import CurrentMatchmakerAdmin
from app.api.routes import (
    customer_leads_admin,
    member_follow_up_admin,
    member_vip_admin,
    merchant_admin,
    offline_vip_admin,
    partner_admin,
    promotion_order_admin,
)
from app.schemas.matchmaker_admin import MatchmakerAdminAccount
from app.schemas.member_vip_admin import AdminVipUpdate
from app.services import customer_lead_admin

SELF_MATCHMAKER_USER_ID = 7
ORGANIZATION_ID = 10


def _admin(
    scope: str,
    *,
    permissions: set[str] | None = None,
    matchmaker_user_id: int | None = SELF_MATCHMAKER_USER_ID,
    organization_id: int | None = ORGANIZATION_ID,
) -> CurrentMatchmakerAdmin:
    return CurrentMatchmakerAdmin(
        account=MatchmakerAdminAccount(
            id=1,
            username="admin",
            display_name="Admin",
            matchmaker_user_id=matchmaker_user_id,
            data_scope=scope,
            organization_id=organization_id,
            status=1,
            last_login_at=None,
        ),
        session_id=1,
        permissions=frozenset(permissions or set()),
    )


class StubResult:
    """最小可用结果对象，按需返回行 / 标量。"""

    def __init__(self, *, rows=None, scalar=None, first=None, one=None, rowcount=0, lastrowid=1):
        self._rows = list(rows or [])
        self._scalar = scalar
        self._first = first
        self._one = one
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def one(self):
        if self._one is None:
            raise AssertionError("one() 未预期被调用")
        return self._one

    def mappings(self):
        return self


class StubDB:
    """记录全部 SQL 的假会话。"""

    def __init__(self, results=None):
        self.statements: list[tuple[str, dict]] = []
        self._results = list(results or [])
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        if self._results:
            return self._results.pop(0)
        return StubResult()

    async def scalar(self, statement, params=None):
        result = await self.execute(statement, params)
        return result.scalar()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def sql(self) -> str:
        return "\n".join(text for text, _ in self.statements)


# --------------------------------------------------------------------------- #
# 第 0 组：作用域逻辑唯一实现 + 路由层无自建分支
# --------------------------------------------------------------------------- #


def test_scope_logic_is_not_reimplemented_in_routes() -> None:
    """D-16 约定：四档判定只在 dependencies.py；路由层不得出现 org_type / parent_id / data_scope 分支。"""
    for module in (
        customer_leads_admin,
        promotion_order_admin,
        partner_admin,
        merchant_admin,
        member_vip_admin,
        offline_vip_admin,
        member_follow_up_admin,
    ):
        source = inspect.getsource(module)
        # 带组织列的资源用 scope_clause，归属只在 resource_assignment 的用 scope_exists_clause；
        # 两者都是 dependencies.py 里的唯一实现，路由层只负责调用。
        assert ("scope_clause" in source or "scope_exists_clause" in source), module.__name__
        assert "data_scope" not in source, f"{module.__name__} 不得直接分支 data_scope"
        assert "org_type" not in source, f"{module.__name__} 不得重写门店判定"
        assert "parent_id" not in source, f"{module.__name__} 不得重写组织层级判定"


def test_all_scoped_routes_apply_exists_predicate() -> None:
    """逐个端点冻结：作用域谓词必须出现在端点自身源码中。"""
    expectations = [
        (customer_leads_admin, ("lead_list", "lead_detail", "lead_update", "lead_abandon", "lead_restore", "abandoned_list")),
        (promotion_order_admin, ("order_list", "order_detail", "order_update", "order_delete", "order_stats")),
        (partner_admin, ("list_partners", "partner_detail", "partner_update", "partner_delete", "list_relations", "remove_relation")),
        (merchant_admin, ("merchant_list", "merchant_detail", "merchant_update", "merchant_delete", "order_list", "order_detail")),
        (member_vip_admin, ("update_member_vip", "vip_members", "login_logs")),
        (offline_vip_admin, ("list_offline_vips", "get_offline_vip", "update_offline_vip", "offline_vip_meet_logs")),
        (member_follow_up_admin, ("all_follow_ups", "follow_up_summary", "list_follow_ups", "create_follow_up", "behavior", "all_behavior")),
    ]
    for module, names in expectations:
        for name in names:
            endpoint = getattr(module, name)
            assert "scope" in inspect.getsource(endpoint), f"{module.__name__}.{name}"


# --------------------------------------------------------------------------- #
# 第 1 组：客源线索（customer_lead）
# --------------------------------------------------------------------------- #


def test_lead_scope_prefixes_columns_for_joined_queries() -> None:
    scope, params = customer_leads_admin._lead_scope(_admin("SELF"))
    assert scope == "matchmaker_id = :scope_matchmaker_user_id"
    assert params == {"scope_matchmaker_user_id": SELF_MATCHMAKER_USER_ID}

    joined_scope, _ = customer_leads_admin._lead_scope(_admin("SELF"), alias="cl.")
    assert joined_scope == "cl.matchmaker_id = :scope_matchmaker_user_id"


@pytest.mark.asyncio
async def test_lead_detail_out_of_scope_is_not_found() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await customer_leads_admin.lead_detail(
            lead_id=99, current=_admin("SELF", permissions={"customer_lead.manage"}), db=db
        )
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment" not in sql  # 客源线索用直列谓词，不是 EXISTS
    assert "matchmaker_id = :scope_matchmaker_user_id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_lead_abandonments_use_joined_alias_scope() -> None:
    db = StubDB([StubResult(rows=[])])
    result = await customer_leads_admin.abandoned_list(
        current=_admin("ORGANIZATION", permissions={"customer_lead.manage"}), db=db
    )
    assert result == []
    sql, params = db.statements[0]
    assert "JOIN customer_lead cl ON cl.id = ab.lead_id" in sql
    assert "cl.organization_id IN (SELECT id FROM organization" in sql
    assert params["scope_organization_id"] == ORGANIZATION_ID


@pytest.mark.asyncio
async def test_lead_detail_is_fail_closed_for_unbound_account() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await customer_leads_admin.lead_detail(
            lead_id=99,
            current=_admin("ORGANIZATION", permissions={"customer_lead.manage"}, matchmaker_user_id=None, organization_id=None),
            db=db,
        )
    assert exc.value.status_code == 404
    assert "1 = 0" in db.statements[0][0]


@pytest.mark.asyncio
async def test_list_leads_binds_scope_params() -> None:
    """服务层收口：作用域谓词进入列表与计数 SQL，且绑定值来自路由层下传。"""
    scope, scope_params = customer_leads_admin._lead_scope(_admin("STORE"))
    db = StubDB([StubResult(rows=[("id",)]), StubResult(rows=[]), StubResult(scalar=0)])
    page = await customer_lead_admin.list_leads(
        db, 1, 20, None, None, None, None,
        scope=scope,
        scope_params=scope_params,
    )
    assert page.total == 0
    assert "organization_id IN (SELECT id FROM organization" in db.sql()
    assert "org_type = 'store'" in db.sql()
    # 计数语句同样带作用域，避免 total 泄露范围外数量。
    count_sql, count_params = db.statements[2]
    assert "scope_store_id" in count_sql
    assert count_params["scope_store_id"] == ORGANIZATION_ID


# --------------------------------------------------------------------------- #
# 第 2 组：推广服务订单（promotion_order）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_promotion_order_detail_scopes_by_buyer_assignment() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await promotion_order_admin.order_detail(
            order_id=99, current=_admin("SELF", permissions={"matchmaker.service.manage"}), db=db
        )
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment.user_id = o.user_id" in sql
    assert "scope_assignment.matchmaker_id = :scope_matchmaker_user_id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_promotion_order_delete_never_commits_out_of_scope() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException):
        await promotion_order_admin.order_delete(
            order_id=99, current=_admin("SELF", permissions={"matchmaker.service.manage"}), db=db
        )
    assert db.committed is False
    assert not any(sql.strip().upper().startswith("DELETE") for sql, _ in db.statements)


# --------------------------------------------------------------------------- #
# 第 3 组：合伙红娘（partner_team / partner_membership）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_partner_detail_scopes_by_team_owner() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await partner_admin.partner_detail(team_id=99, current=_admin("SELF", permissions={"matchmaker.manage"}), db=db)
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment.user_id = t.owner_user_id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_partner_delete_never_commits_out_of_scope() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException):
        await partner_admin.partner_delete(team_id=99, current=_admin("SELF", permissions={"matchmaker.manage"}), db=db)
    assert db.committed is False
    assert not any("UPDATE partner_membership" in sql for sql, _ in db.statements)


@pytest.mark.asyncio
async def test_partner_relation_remove_joins_team_for_scope() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await partner_admin.remove_relation(
            relation_id=5,
            body=partner_admin.service.PartnerRelationRemove(reason="越权测试"),
            current=_admin("SELF", permissions={"matchmaker.manage"}),
            db=db,
        )
    assert exc.value.status_code == 404
    sql = db.statements[0][0]
    assert "LEFT JOIN partner_team t ON t.id = pm.team_id" in sql
    assert "scope_assignment.user_id = t.owner_user_id" in sql


# --------------------------------------------------------------------------- #
# 第 4 组：商家联盟（merchant）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_merchant_detail_scopes_by_admin_user() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await merchant_admin.merchant_detail(
            merchant_id=99, current=_admin("SELF", permissions={"merchant.manage"}), db=db
        )
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment.user_id = m.admin_user_id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_merchant_orders_scope_uses_merchant_join_in_count_query() -> None:
    """计数语句必须补上 merchant join，否则 EXISTS 谓词会因缺别名而报错。"""
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    await merchant_admin.order_list(
        page=1,
        page_size=20,
        merchant_id=None,
        status=None,
        verify_status=None,
        keyword=None,
        order_no=None,
        buyer_keyword=None,
        verify_start=None,
        verify_end=None,
        search_type=None,
        current=_admin("ORGANIZATION", permissions={"merchant.manage"}),
        db=db,
    )
    count_sql = db.statements[1][0]
    assert "LEFT JOIN merchant m ON m.id = o.merchant_id" in count_sql
    assert "scope_assignment.organization_id IN (SELECT id FROM organization" in count_sql


@pytest.mark.asyncio
async def test_merchant_create_rolls_back_when_new_row_is_out_of_scope() -> None:
    """新增行落在范围外（如绑定他人管理账号）时必须回滚，不落库。"""
    db = StubDB([StubResult(lastrowid=77), StubResult(first=None)])
    body = merchant_admin.MerchantCreate(name="越权商家")
    with pytest.raises(HTTPException) as exc:
        await merchant_admin.merchant_create(
            body=body, current=_admin("SELF", permissions={"merchant.manage"}), db=db
        )
    assert exc.value.status_code == 404
    assert db.rolled_back is True
    assert db.committed is False


# --------------------------------------------------------------------------- #
# 第 5 组：会员 VIP / 线下 VIP / 会员跟进
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_member_vip_update_out_of_scope_never_writes() -> None:
    db = StubDB([StubResult(scalar=None)])
    with pytest.raises(HTTPException) as exc:
        await member_vip_admin.update_member_vip(
            member_id=99,
            body=AdminVipUpdate(action="CANCEL", reason="越权测试"),
            current=_admin("SELF", permissions={"matchmaker.member.manage"}),
            db=db,
        )
    assert exc.value.status_code == 404
    assert len(db.statements) == 1
    assert "scope_assignment.user_id = users.id" in db.statements[0][0]
    assert db.committed is False


@pytest.mark.asyncio
async def test_offline_vip_detail_scopes_by_member_assignment() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await offline_vip_admin.get_offline_vip(
            vip_id=99, current=_admin("SELF", permissions={"matchmaker.member.manage"}), db=db
        )
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment.user_id = v.user_id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_offline_vip_update_never_commits_out_of_scope() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException):
        await offline_vip_admin.update_offline_vip(
            vip_id=99,
            body=offline_vip_admin.OfflineVipUpdate(remark="越权测试"),
            current=_admin("SELF", permissions={"matchmaker.member.manage"}),
            db=db,
        )
    assert db.committed is False
    assert not any("UPDATE offline_vip SET" in sql for sql, _ in db.statements)


@pytest.mark.asyncio
async def test_member_follow_up_out_of_scope_member_is_not_found() -> None:
    db = StubDB([StubResult(scalar=None)])
    with pytest.raises(HTTPException) as exc:
        await member_follow_up_admin.list_follow_ups(
            member_id=99,
            page=1,
            page_size=20,
            current=_admin("SELF", permissions={"matchmaker.member.manage"}),
            db=db,
        )
    assert exc.value.status_code == 404
    sql, params = db.statements[0]
    assert "scope_assignment.user_id = users.id" in sql
    assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID


@pytest.mark.asyncio
async def test_member_follow_up_behavior_is_scoped_in_every_branch() -> None:
    """行为流水各分类分支都必须带作用域谓词，避免聚合视图绕过数据范围。"""
    for category in ("browse", "favorite", "superlike", "report"):
        db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
        await member_follow_up_admin.all_behavior(
            page=1,
            page_size=20,
            search=None,
            category=category,
            min_times=None,
            status=None,
            current=_admin("SELF", permissions={"matchmaker.member.manage"}),
            db=db,
        )
        sql, params = db.statements[0]
        assert "scope_assignment.user_id = u.id" in sql, category
        assert params["scope_matchmaker_user_id"] == SELF_MATCHMAKER_USER_ID, category


@pytest.mark.asyncio
async def test_member_follow_up_summary_is_fail_closed_when_unbound() -> None:
    db = StubDB([StubResult(one={key: 0 for key in (
        "all_count", "today_count", "yesterday_count", "three_days_count",
        "this_week_count", "last_week_count", "this_month_count", "last_month_count",
    )})])
    await member_follow_up_admin.follow_up_summary(
        current=_admin("ORGANIZATION", permissions={"matchmaker.member.manage"}, matchmaker_user_id=None, organization_id=None),
        db=db,
    )
    assert "1 = 0" in db.statements[0][0]


# --------------------------------------------------------------------------- #
# TODO：真实多组织账号端到端越权验证
# --------------------------------------------------------------------------- #
# 以下场景需要隔离 MySQL（两组织 A / B，各自门店、红娘、会员），本机不可用：
#   1. A 门店账号 GET /admin/customer-leads 不返回 B 门店线索；
#   2. A 门店账号 PATCH /admin/customer-leads/{B的线索} 返回 404 且库中无变化；
#   3. A 组织账号 DELETE /admin/merchants/{B的商家} 返回 404；
#   4. A 门店账号 POST /admin/members/{B会员}/vip 返回 404；
#   5. A 门店账号 GET /admin/merchant-orders/export 导出行数与列表 total 一致。
