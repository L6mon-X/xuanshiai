"""F15 等四项后端缺口修复回归（2026-10-31）。

覆盖：
1. F15 分店红娘菜单权限：`menu_permission_count` 无法区分「未配置(默认全部)」与
   「手动清空(无权限)」，补 `menu_permission_configured`；state 表缺失时必须降级不 500。
2. 牵线记录「操作人」筛选：`operator_id` 是 `matchmaker_id` 的语义别名，列表与统计同口径。
3. 线下VIP「搜索类型」：`search_by` 只收服务端白名单，未知值退化为综合搜索。
4. 会员弃海记录：放弃人/捞取人/捞取时间可直接展示（补昵称与会员编号）。
5. 客源线索编辑：补 `source`，已下线的 `tags` 显式 422 而非静默丢弃。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes import matchmaker_crm_admin as crm_routes
from app.main import app
from app.schemas.customer_lead_admin import CustomerLeadUpdate
from app.services import matchmaker_staff_admin as staff
from app.services import offline_vip_admin as vip

SPEC = app.openapi()


class _Result:
    """最小结果对象：同时支撑 all()/scalar()/mappings()/first()。"""

    def __init__(self, *, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self


class _DB:
    """按调用顺序吐出预置结果，并记录实际下发的 SQL 与参数。"""

    def __init__(self, results=None, scalar=None):
        self._results = list(results or [])
        self._scalar = scalar
        self.statements: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        return self._results.pop(0) if self._results else _Result()

    async def scalar(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        return self._scalar

    def sql(self) -> str:
        return "\n".join(statement for statement, _ in self.statements)

    def params(self) -> list[dict]:
        return [params for _, params in self.statements]


# ── F15 菜单权限已配置信号 ────────────────────────────────────────


def test_staff_item_exposes_menu_permission_configured() -> None:
    props = SPEC["components"]["schemas"]["MatchmakerStaffItem"]["properties"]
    assert "menu_permission_configured" in props
    assert "menu_permission_count" in props


def test_permissions_contract_exposes_configured() -> None:
    props = SPEC["components"]["schemas"]["MatchmakerPermissions"]["properties"]
    assert "configured" in props
    assert "menuIds" in props


@pytest.mark.asyncio
async def test_staff_select_degrades_when_state_table_missing() -> None:
    # information_schema 探测返回空 → 不引用 state 表，配置标记恒为 0（未配置）。
    db = _DB(results=[_Result(scalar=None)])
    sql = await staff._staff_select(db)
    assert "matchmaker_menu_permission_state" not in sql
    assert "(CASE WHEN 0 THEN 1 ELSE 0 END) menu_permission_configured" in sql


@pytest.mark.asyncio
async def test_staff_select_reads_state_table_when_present() -> None:
    db = _DB(results=[_Result(scalar=1)])
    sql = await staff._staff_select(db)
    assert "matchmaker_menu_permission_state st" in sql
    # 存量已赋菜单但没有 state 行的红娘同样算「已配置」，避免升级后权限被当成全部菜单。
    assert "mmp2.matchmaker_user_id = u.id) > 0" in sql


@pytest.mark.asyncio
async def test_permission_configured_reads_state_row() -> None:
    db = _DB(results=[_Result(scalar=1), _Result(scalar=1)])
    assert await staff._permission_configured(db, 7) is True
    db = _DB(results=[_Result(scalar=1), _Result(scalar=None)])
    assert await staff._permission_configured(db, 7) is False


def test_staff_item_passes_permission_fields_through() -> None:
    item = staff._item(
        {
            "id": 11,
            "nickname": "小满",
            "menu_permission_count": 0,
            "menu_permission_configured": 1,
            "contact_editable": 1,
        }
    )
    assert item.menu_permission_count == 0
    assert item.menu_permission_configured is True


# ── 牵线记录「操作人」筛选 ────────────────────────────────────────


def test_match_records_expose_operator_id() -> None:
    for path in ("/api/v1/admin/matchmaker/match-records", "/api/v1/admin/matchmaker/match-records/statistics"):
        params = {item["name"] for item in SPEC["paths"][path]["get"]["parameters"]}
        assert "operator_id" in params
        assert "matchmaker_id" in params


class _Current:
    """只实现数据范围谓词的最小当前账号。"""

    def scope_exists_clause(self, params, *, correlation, **kwargs):
        return "1=1"


@pytest.mark.asyncio
async def test_operator_id_filters_match_records() -> None:
    db = _DB(results=[_Result(rows=[]), _Result(scalar=0)])
    await crm_routes.match_records(
        page=1,
        page_size=20,
        search=None,
        keyword=None,
        search_type=None,
        date_from=None,
        date_to=None,
        matchmaker_id=None,
        operator_id=9,
        status_group=None,
        current=_Current(),
        db=db,
    )
    assert "ra.matchmaker_id = :matchmaker_id" in db.sql()
    assert db.params()[0]["matchmaker_id"] == 9


# ── 线下VIP「搜索类型」 ──────────────────────────────────────────


def test_offline_vip_exposes_search_by() -> None:
    params = {item["name"] for item in SPEC["paths"]["/api/v1/admin/offline-vips"]["get"]["parameters"]}
    assert "search_by" in params


def test_search_by_whitelist() -> None:
    assert set(vip._SEARCH_BY_SQL) == {"all", "nickname", "phone", "code", "real_name"}


@pytest.mark.asyncio
async def test_search_by_restricts_keyword_columns() -> None:
    db = _DB(results=[_Result(rows=[])], scalar=0)
    await vip.list_vips(db, 1, 20, keyword="1380", search_by="phone")
    sql = db.sql()
    assert "u.phone LIKE CONCAT('%', :keyword, '%')" in sql
    assert "u.nickname LIKE" not in sql


@pytest.mark.asyncio
async def test_unknown_search_by_falls_back_to_all_columns() -> None:
    db = _DB(results=[_Result(rows=[])], scalar=0)
    await vip.list_vips(db, 1, 20, keyword="1380", search_by="unknown")
    assert "u.nickname LIKE" in db.sql()


# ── 会员弃海记录：放弃人 / 捞取人 / 捞取时间 ─────────────────────


def test_member_abandonment_item_has_actor_names() -> None:
    props = SPEC["components"]["schemas"]["MemberAbandonmentItem"]["properties"]
    assert {
        "abandoned_by_name",
        "restored_by_name",
        "restored_at",
        "member_code",
        "phone",
        "assigned_matchmaker_name",
    } <= set(props)


# ── 客源线索编辑：source 可改，tags 显式 422 ──────────────────────


def test_customer_lead_update_accepts_source() -> None:
    body = CustomerLeadUpdate(source="抖音")
    assert body.model_dump(exclude_unset=True) == {"source": "抖音"}


def test_customer_lead_update_rejects_retired_tags() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CustomerLeadUpdate(tags=["高意向"])
    assert "标签功能已下线" in str(excinfo.value)
