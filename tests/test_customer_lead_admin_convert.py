"""后台一键入库（admin/customer-leads/{id}/convert）回归。

修复点：后台入库此前只有红娘工作台路由，操作人无法在后台选择会员归属。
钉住新契约：
1. 归属优先取本次请求，其次沿用线索已有分派，两处都没有 → 422 且不建账号；
2. 归属必须通过 _validate_owner 校验（有效服务红娘 / 启用门店）；
3. 手机号已存在会员 → 409 可读提示，不抛数据库唯一键异常；
4. 已入库、已关闭、已弃海、无手机号的客源不能入库；
5. 手机号不是有效 11 位号码的客源 → 422，且不建账号；
6. 四张表写入内容与归属回写（users / member_review / resource_assignment / customer_lead）；
7. 连点两次入库撞唯一键时转 409，不冒 500。
全部用 StubDB 按 SQL 文本分派结果，走真实 service 逻辑，不依赖 MySQL。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.customer_lead_admin import CustomerLead, CustomerLeadConvertRequest
from app.services.customer_lead_admin import LEAD_SELECT, convert_lead

PHONE = "13800000000"
NOW = datetime(2026, 10, 1, 12, 0, 0)
NEW_USER_ID = 4200


class StubResult:
    def __init__(self, *, first=None, scalar=None, lastrowid=None):
        self._first = first
        self._scalar = scalar
        self.lastrowid = lastrowid

    def all(self):
        return []

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def mappings(self):
        return self


class _Nested:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class StubDB:
    """按 SQL 特征分派返回值，因此不同校验分支不会因查询条数不同而错位。"""

    def __init__(self, lead_row: dict, *, owner_ok: bool = True, phone_taken_by: int | None = None, conflict_on_user_insert: bool = False):
        self.statements: list[tuple[str, dict]] = []
        self.committed = False
        self.rolled_back = False
        self._lead_row = lead_row
        self._owner_ok = owner_ok
        self._phone_taken_by = phone_taken_by
        self._conflict = conflict_on_user_insert

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, dict(params or {})))
        if "tags_raw" in sql:
            return StubResult(first=self._lead_row)
        if "role_code = 'service_matchmaker'" in sql:
            return StubResult(scalar=1 if self._owner_ok else None)
        if "org_type = 'store'" in sql:
            return StubResult(scalar=1)
        if "FROM users WHERE phone" in sql:
            return StubResult(scalar=self._phone_taken_by)
        if "INSERT INTO users" in sql:
            if self._conflict:
                raise IntegrityError(sql, {}, RuntimeError("Duplicate entry for key 'uk_phone'"))
            return StubResult(lastrowid=NEW_USER_ID)
        return StubResult()

    def begin_nested(self) -> _Nested:
        return _Nested()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    def sql(self) -> str:
        return "\n".join(text for text, _ in self.statements)

    def params_for(self, needle: str) -> dict:
        return next(params for sql, params in self.statements if needle in sql)


def _lead_row(**overrides) -> dict:
    row = {
        "id": 3, "name": "张女士", "real_name": None, "phone": PHONE, "wechat": None,
        "source": "抖音", "photo": None, "gender": 2, "birthday": None,
        "intention_level": 2, "status": "NEW", "audit_status": "active",
        "matchmaker_id": None, "organization_id": None, "promoter_id": None,
        "next_follow_at": None, "converted_user_id": None, "remark": None,
        "created_by": 1, "created_at": NOW, "updated_at": NOW, "tags_raw": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_convert_requires_an_owner_before_creating_the_member() -> None:
    db = StubDB(_lead_row())
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest())
    assert err.value.status_code == 422
    assert "归属" in err.value.detail
    # 校验发生在写库之前，一条写入都不该落下
    assert "INSERT INTO users" not in db.sql()
    assert db.committed is False


@pytest.mark.asyncio
async def test_convert_validates_the_operator_selected_owner() -> None:
    db = StubDB(_lead_row(), owner_ok=False)
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7, organization_id=9))
    assert err.value.status_code == 422
    assert "服务红娘" in err.value.detail
    assert "INSERT INTO users" not in db.sql()


@pytest.mark.asyncio
async def test_convert_writes_member_with_the_selected_owner() -> None:
    db = StubDB(_lead_row())
    result = await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7, organization_id=9))
    assert result.user_id == NEW_USER_ID
    assert result.review_status == "PENDING"
    assert db.committed is True

    assert db.params_for("INSERT INTO users") == {
        "openid": "lead-convert-3", "phone": PHONE, "nickname": "张女士", "gender": 2,
    }
    assert db.params_for("INSERT INTO matchmaker_member_review") == {"user_id": NEW_USER_ID}
    assert db.params_for("INSERT INTO resource_assignment") == {
        "user_id": NEW_USER_ID, "organization_id": 9, "matchmaker_id": 7, "assigned_by": 1,
    }
    assert "'lead_convert'" in db.sql()
    assert db.params_for("UPDATE customer_lead SET status = 'CONVERTED'") == {
        "user_id": NEW_USER_ID, "matchmaker_id": 7, "organization_id": 9, "lead_id": 3,
    }
    assert db.params_for("customer_lead.convert")["actor"] == 1


@pytest.mark.asyncio
async def test_convert_falls_back_to_the_lead_owner_and_keeps_gender_overridable() -> None:
    db = StubDB(_lead_row(matchmaker_id=7, organization_id=9))
    await convert_lead(db, 1, 3, CustomerLeadConvertRequest(gender=1))
    assignment = db.params_for("INSERT INTO resource_assignment")
    assert assignment["matchmaker_id"] == 7 and assignment["organization_id"] == 9
    assert db.params_for("INSERT INTO users")["gender"] == 1


@pytest.mark.asyncio
async def test_convert_reports_existing_member_instead_of_a_unique_key_error() -> None:
    db = StubDB(_lead_row(), phone_taken_by=55)
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7))
    assert err.value.status_code == 409
    assert "55" in err.value.detail
    assert "INSERT INTO users" not in db.sql()


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    _lead_row(status="CONVERTED", converted_user_id=88),
    _lead_row(status="CONVERTED"),
    _lead_row(status="CLOSED"),
    _lead_row(status="LOST"),
    _lead_row(phone=None),
])
async def test_convert_refuses_leads_that_cannot_become_members(row: dict) -> None:
    db = StubDB(row)
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7))
    assert err.value.status_code == 409
    assert "INSERT INTO users" not in db.sql()
    assert db.committed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("phone", [
    "12345678901",  # 首位不是 13-19
    "1380000000",  # 只有 10 位
    "138 0000 0000",  # 带空格
    "wx_zhang",  # 微信号被当成电话录进历史线索
])
async def test_convert_blocks_an_unusable_lead_phone_before_creating_the_member(phone: str) -> None:
    """入库直接拿手机号建会员账号，微信-only/占位号码必须当场挡住，否则留下登不进来的号。"""
    db = StubDB(_lead_row(phone=phone))
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7))
    assert err.value.status_code == 422
    assert phone in err.value.detail
    assert "INSERT INTO users" not in db.sql()
    assert db.committed is False


def test_lead_select_provides_every_required_customer_lead_field() -> None:
    """LEAD_SELECT 少选一列，客源列表/详情/入库全部 500（Pydantic: Field required）。"""
    required = {name for name, field in CustomerLead.model_fields.items() if field.is_required()}
    assert required, "CustomerLead 应有必填字段"
    assert {name for name in required if name not in LEAD_SELECT} == set()


@pytest.mark.asyncio
async def test_convert_maps_a_duplicate_key_race_to_a_readable_conflict() -> None:
    """撞库检查到写库之间被另一个请求抢先入库时，唯一键异常转成 409，不冒 500。"""
    db = StubDB(_lead_row(), conflict_on_user_insert=True)
    with pytest.raises(HTTPException) as err:
        await convert_lead(db, 1, 3, CustomerLeadConvertRequest(matchmaker_id=7))
    assert err.value.status_code == 409
    assert db.rolled_back is True
    assert db.committed is False
