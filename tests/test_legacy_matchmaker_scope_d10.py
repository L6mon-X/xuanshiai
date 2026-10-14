"""D-10 / D-9 回归：旧版红娘后台门店/资源分配/申请审核路由的数据范围与敏感操作幂等。

D-10：`/admin/matchmaker/branches`、`/admin/matchmaker/assignments`、门店加成员、
红娘申请审核列表/详情此前**无数据范围过滤**（`GET /assignments` 直接 `1=1`），
任意门店管理员都能看到全平台数据。本文件按四档语义逐一回归。

D-9：资源分配纳入统一敏感操作（`require_sensitive_operation` + `sensitive_operations`），
越权在幂等预占之前拦截，不留幂等残留行。

验收口径：A 组织账号访问 B 组织数据 → 0 条或 403/404；未绑定组织 → 1 = 0（fail-closed）。
"""

from __future__ import annotations

import inspect
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.dependencies import CurrentMatchmakerAdmin, require_sensitive_operation
from app.api.routes import identity as identity_routes
from app.api.routes import matchmaker_admin
from app.schemas.matchmaker_admin import MatchmakerAdminAccount
from app.schemas.organization import ResourceAssignmentCreate, StoreMemberCreate

MATCHMAKER_USER_ID = 7
ORGANIZATION_ID = 10
_NOW = datetime(2026, 10, 11, 12, 0, 0)


def _admin(scope: str, *, permissions: set[str] | None = None, matchmaker_user_id: int | None = MATCHMAKER_USER_ID, organization_id: int | None = ORGANIZATION_ID) -> CurrentMatchmakerAdmin:
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
        return (await self.execute(statement, params)).scalar()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def sql(self) -> str:
        return "\n".join(text for text, _ in self.statements)


# --------------------------------------------------------------------------- #
# D-10 门店（/branches）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_legacy_branch_list_is_scoped() -> None:
    db = StubDB([StubResult(rows=[])])
    out = await matchmaker_admin.branches(current=_admin("ORGANIZATION"), db=db)
    assert out == []
    assert "id IN (SELECT id FROM organization" in db.statements[0][0]
    assert db.statements[0][1]["scope_organization_id"] == ORGANIZATION_ID


@pytest.mark.asyncio
async def test_legacy_branch_list_fail_closed_when_unbound() -> None:
    db = StubDB([StubResult(rows=[])])
    await matchmaker_admin.branches(current=_admin("ORGANIZATION", organization_id=None), db=db)
    assert "1 = 0" in db.statements[0][0]


@pytest.mark.asyncio
async def test_legacy_branch_detail_hides_out_of_scope_store() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await matchmaker_admin.branch_detail(branch_id=99, current=_admin("SELF"), db=db)
    assert exc.value.status_code == 404
    # SELF 档对「组织自有资源」一无所见（1 = 0），而非按个人 ID 匹配组织 ID。
    assert "1 = 0" in db.statements[0][0]


@pytest.mark.asyncio
async def test_legacy_branch_member_add_guards_scope_before_write() -> None:
    db = StubDB([StubResult(first=None)])
    body = StoreMemberCreate(user_id=5, role_code="store_matchmaker")
    with pytest.raises(HTTPException) as exc:
        await matchmaker_admin.branch_member(
            branch_id=99, body=body, current=_admin("ORGANIZATION"), db=db
        )
    assert exc.value.status_code == 404
    assert not any("INSERT INTO organization_member" in s for s, _ in db.statements)


# --------------------------------------------------------------------------- #
# D-10 资源分配（/assignments）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_legacy_assignment_list_is_scoped_by_self() -> None:
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    page = await matchmaker_admin.assignments(
        page=1, page_size=20, user_id=None, matchmaker_id=None, current=_admin("SELF"), db=db
    )
    assert page.total == 0
    sql = db.statements[0][0]
    assert "matchmaker_id = :scope_matchmaker_user_id" in sql
    # 回归：历史实现为无条件 1=1，任何门店账号都能列出全平台分配。
    assert "1=1" not in sql.replace(" ", "")


@pytest.mark.asyncio
async def test_legacy_assignment_list_fail_closed_when_unbound() -> None:
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    await matchmaker_admin.assignments(
        page=1, page_size=20, user_id=None, matchmaker_id=None,
        current=_admin("ORGANIZATION", organization_id=None), db=db,
    )
    assert "1 = 0" in db.statements[0][0]


@pytest.mark.asyncio
async def test_legacy_assignment_list_platform_account_is_unrestricted() -> None:
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    await matchmaker_admin.assignments(
        page=1, page_size=20, user_id=None, matchmaker_id=None, current=_admin("ALL"), db=db
    )
    assert "1 = 1" in db.statements[0][0]


@pytest.mark.asyncio
async def test_legacy_assignment_create_rejects_out_of_scope_store() -> None:
    db = StubDB([StubResult(scalar=0)])
    body = ResourceAssignmentCreate(user_id=1, organization_id=99)
    with pytest.raises(HTTPException) as exc:
        await matchmaker_admin.assignment(
            body=body, idempotency_key="assign-test-key", current=_admin("ORGANIZATION"), db=db
        )
    assert exc.value.status_code == 403
    # 越权在幂等预占之前拦截，不留幂等残留行。
    assert not any("api_idempotency_record" in s for s, _ in db.statements)


@pytest.mark.asyncio
async def test_legacy_assignment_create_rejects_out_of_scope_matchmaker() -> None:
    db = StubDB([StubResult(scalar=0)])
    body = ResourceAssignmentCreate(user_id=1, matchmaker_id=77)
    with pytest.raises(HTTPException) as exc:
        await matchmaker_admin.assignment(
            body=body, idempotency_key="assign-test-key", current=_admin("SELF"), db=db
        )
    assert exc.value.status_code == 403
    assert not any("api_idempotency_record" in s for s, _ in db.statements)


def test_legacy_assignment_route_declares_sensitive_operation() -> None:
    """D-9：资源分配必须走统一敏感操作依赖（Idempotency-Key + confirm）。"""
    default = inspect.signature(matchmaker_admin.assignment).parameters["idempotency_key"].default
    assert default is not inspect.Parameter.empty
    assert getattr(default, "dependency", None) is require_sensitive_operation
    assert "matchmaker.assignment.create" in inspect.getsource(matchmaker_admin.assignment)


# --------------------------------------------------------------------------- #
# D-10 红娘申请审核（/admin/matchmaker/applications）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_application_list_is_scoped() -> None:
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    payload = await identity_routes.admin_matchmaker_applications(
        page=1, page_size=20, application_type=None, status=None, search=None,
        admin=_admin("SELF", permissions={"matchmaker.application.read"}), db=db,
    )
    assert payload["total"] == 0
    sql = db.statements[0][0]
    assert "scope_assignment.matchmaker_id = :scope_matchmaker_user_id" in sql
    assert "scope_assignment.user_id = user_matchmaker_apply.user_id" in sql


@pytest.mark.asyncio
async def test_application_detail_out_of_scope_is_404() -> None:
    db = StubDB([StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        await identity_routes.admin_matchmaker_application_detail(
            application_id=99,
            admin=_admin("STORE", permissions={"matchmaker.application.read"}), db=db,
        )
    assert exc.value.status_code == 404
    assert "scope_assignment.organization_id IN (SELECT id FROM organization" in db.statements[0][0]


@pytest.mark.asyncio
async def test_application_list_fail_closed_when_unbound() -> None:
    db = StubDB([StubResult(rows=[]), StubResult(scalar=0)])
    await identity_routes.admin_matchmaker_applications(
        page=1, page_size=20, application_type=None, status=None, search=None,
        admin=_admin("ORGANIZATION", organization_id=None, permissions={"matchmaker.application.read"}),
        db=db,
    )
    assert "1 = 0" in db.statements[0][0]
