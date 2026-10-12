"""审计第 2b 项回归：本店改派后会员仍须本店可见。

历史缺陷：改派 INSERT 不写 ``organization_id``，新 ``resource_assignment`` 行组织归属
为空，STORE 档 ``scope_assignment.organization_id`` 谓词匹配不到 → 本店改派后反而
看不到该会员。断言真链路 route → SQL：INSERT 列与绑定值必须带操作人门店组织。
"""

from __future__ import annotations

import re

import pytest
from fastapi import HTTPException

import app.api.routes.matchmaker_crm_admin as crm
from app.api.dependencies import CurrentMatchmakerAdmin
from app.schemas.matchmaker_admin import MatchmakerAdminAccount
from app.schemas.matchmaker_crm_admin import MemberAssignmentUpdate

PLACEHOLDER = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


class StubResult:
    def __init__(self, *, scalar=None, first=None, rowcount=0, lastrowid=1):
        self._scalar = scalar
        self._first = first
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def mappings(self):
        return self


class StubDB:
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

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


# D-9：改派已纳入统一幂等（`require_sensitive_operation` + sensitive_operations），
# 直调服务层的单元测试需显式补上 `idempotency_key`。
IDEMPOTENCY_KEY = "reassign-test-key"


def _reserve_result() -> StubResult:
    """幂等预占 INSERT 的桩结果（需要 lastrowid）。"""
    return StubResult(lastrowid=1)


def _complete_result() -> StubResult:
    """幂等完成 UPDATE 的桩结果（complete 要求 rowcount == 1）。"""
    return StubResult(rowcount=1)


def _store_admin(organization_id: int = 88) -> CurrentMatchmakerAdmin:
    return CurrentMatchmakerAdmin(
        account=MatchmakerAdminAccount(
            id=4, username="store-ops", display_name="门店运营", matchmaker_user_id=7,
            data_scope="STORE", organization_id=organization_id, status=1, last_login_at=None,
        ),
        session_id=1,
        permissions=frozenset({"matchmaker.member.manage"}),
    )


@pytest.mark.asyncio
async def test_reassignment_insert_carries_operator_organization() -> None:
    db = StubDB([
        StubResult(scalar=9),    # 范围守卫：会员可见
        StubResult(scalar=1),    # 目标服务红娘有效
        _reserve_result(),       # D-9：幂等预占 INSERT
        StubResult(),            # 结束旧 assignment
        StubResult(),            # 新 assignment INSERT
        StubResult(),            # 审计
        _complete_result(),      # D-9：幂等完成 UPDATE
    ])
    out = await crm.member_assignment(
        member_id=9, body=MemberAssignmentUpdate(matchmaker_id=77),
        idempotency_key=IDEMPOTENCY_KEY,
        current=_store_admin(organization_id=88), db=db,
    )
    assert out.matchmaker_id == 77
    insert_sql, insert_params = next(
        (s, p) for s, p in db.statements if "INSERT INTO resource_assignment" in s
    )
    # 组织列缺失或绑定为空都会让本店 STORE 谓词匹配不到新行
    assert "organization_id" in insert_sql
    assert insert_params.get("organization_id") == 88
    assert insert_params["matchmaker_id"] == 77
    assert insert_params["assigned_by"] == 4
    assert db.committed is True
    # 幂等键与 operation 必须落到预占行，改派才可安全重放。
    reserve_sql, reserve_params = db.statements[2]
    assert "INSERT INTO api_idempotency_record" in reserve_sql
    assert reserve_params["operation"] == "matchmaker.member.reassign"
    assert reserve_params["idempotency_key"] == IDEMPOTENCY_KEY


@pytest.mark.asyncio
async def test_reassignment_guard_sql_placeholders_all_bound() -> None:
    """守卫谓词与绑定参数必须成对：STORE 档用 scope_store_id 绑定门店组织。"""
    db = StubDB([
        StubResult(scalar=9), StubResult(scalar=1),
        _reserve_result(), StubResult(), StubResult(), StubResult(), _complete_result(),
    ])
    await crm.member_assignment(
        member_id=9, body=MemberAssignmentUpdate(matchmaker_id=77),
        idempotency_key=IDEMPOTENCY_KEY,
        current=_store_admin(organization_id=88), db=db,
    )
    sql, params = db.statements[0]
    assert set(PLACEHOLDER.findall(sql)) <= set(params)
    assert params["scope_store_id"] == 88


@pytest.mark.asyncio
async def test_reassignment_of_out_of_scope_member_writes_nothing() -> None:
    db = StubDB([StubResult(scalar=None)])
    with pytest.raises(HTTPException) as exc:
        await crm.member_assignment(
            member_id=9, body=MemberAssignmentUpdate(matchmaker_id=77),
            idempotency_key=IDEMPOTENCY_KEY,
            current=_store_admin(), db=db,
        )
    assert exc.value.status_code == 404
    # 守卫 SQL 的 scope 子句本身就 join resource_assignment，只断言没有任何写语句
    assert not any(
        "INSERT INTO resource_assignment" in s or "UPDATE resource_assignment" in s
        for s, _ in db.statements
    )
    # 越权在幂等预占之前就被拦截，不得留下幂等残留行。
    assert not any("api_idempotency_record" in s for s, _ in db.statements)
    assert db.committed is False


@pytest.mark.asyncio
async def test_cancel_assignment_inserts_no_row() -> None:
    """matchmaker_id=null 只结束旧分派，不得插入 organization_id 为空的新行。"""
    db = StubDB([
        StubResult(scalar=9), _reserve_result(), StubResult(), StubResult(), _complete_result(),
    ])
    await crm.member_assignment(
        member_id=9, body=MemberAssignmentUpdate(matchmaker_id=None),
        idempotency_key=IDEMPOTENCY_KEY,
        current=_store_admin(), db=db,
    )
    assert not any("INSERT INTO resource_assignment" in s for s, _ in db.statements)
    assert any("UPDATE resource_assignment SET status = 2" in s for s, _ in db.statements)
    assert db.committed is True
