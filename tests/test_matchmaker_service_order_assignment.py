"""私人定制下单：matchmaker_id 缺省时由服务端分配（2026-11-02，Q79）。

修复前的故障：前端 ``api/matchmaker.uts`` 提交的字段里没有 ``matchmaker_id``，
而后端 ``MatchmakerServiceOrderCreate`` 把它设为必填 → 稳定 422「无法申请私人定制」。

本文件锁定：
1. 契约：缺省 ``matchmaker_id`` 合法，``assignment_mode=designated`` 时必须给；
2. 分配：按在办订单数升序取一名可用服务红娘，池空返回 503（不是 404）；
3. 落地：``create_service_order`` 真正把分配结果写进订单，而不是继续用 None。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dependencies import CurrentUser
from app.schemas.matchmaker import MatchmakerServiceOrderCreate
from app.services import matchmaker as service


def _current(user_id: int = 10) -> CurrentUser:
    return CurrentUser(
        id=user_id,
        session_id=1,
        phone="13100000000",
        status=1,
        realname_status=2,
    )


def _request(**overrides: Any) -> MatchmakerServiceOrderCreate:
    payload: dict[str, Any] = {
        "product_id": 4,
        "requirement": "希望找一位同城、本科以上、喜欢户外的伴侣",
    }
    payload.update(overrides)
    return MatchmakerServiceOrderCreate.model_validate(payload)


def test_matchmaker_id_is_optional() -> None:
    body = _request()
    assert body.matchmaker_id is None
    assert body.assignment_mode == "auto"


def test_designated_requires_matchmaker_id() -> None:
    with pytest.raises(ValidationError):
        _request(assignment_mode="designated")


def test_matchmaker_id_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _request(matchmaker_id=0)


class _Result:
    def __init__(self, row: dict[str, Any] | None = None, lastrowid: int | None = None) -> None:
        self._row = row
        self.lastrowid = lastrowid

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return dict(self._row) if self._row else None

    def one(self) -> dict[str, Any]:
        assert self._row is not None
        return dict(self._row)

    def scalar(self) -> Any:
        return self._row


class _RecordingDb:
    """按脚本顺序出结果，同时记录每次 execute 的 SQL 与参数。"""

    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.committed = False

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((str(statement), dict(params or {})))
        return self.results.pop(0) if self.results else _Result()

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_assign_picks_least_loaded_matchmaker(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _RecordingDb(_Result({"user_id": 21, "active_orders": 0}))

    assigned = await service.assign_service_matchmaker(db, exclude_user_id=10)

    assert assigned == 21
    statement, params = db.calls[0]
    assert "ORDER BY active_orders ASC" in statement
    assert params["exclude_user_id"] == 10


@pytest.mark.asyncio
async def test_assign_returns_503_when_pool_empty() -> None:
    db = _RecordingDb(_Result(None))

    with pytest.raises(HTTPException) as error:
        await service.assign_service_matchmaker(db)

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_order_uses_assigned_matchmaker_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_assign(_db: Any, *, exclude_user_id: int | None = None) -> int:
        assert exclude_user_id == 10
        return 21

    async def fake_interact(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(service, "assign_service_matchmaker", fake_assign)
    monkeypatch.setattr(service, "ensure_users_can_interact", fake_interact)

    created_row = {
        "id": 7,
        "order_no": "XM2026110200000010abcd",
        "user_id": 10,
        "matchmaker_id": 21,
        "service_product_id": 4,
        "service_type": 3,
        "product_name": "私人定制",
        "amount": Decimal("1999.00"),
        "status": 0,
        "service_request_id": None,
        "created_at": datetime(2026, 11, 2, 9, 0, 0),
        "pay_time": None,
    }
    db = _RecordingDb(
        _Result({"user_id": 21}),                                     # 红娘存在性校验
        _Result({"id": 4, "name": "私人定制", "service_type": 3, "price": Decimal("1999.00")}),
        _Result(None),                                                # 同键订单不存在
        _Result(lastrowid=7),                                         # INSERT
        _Result(created_row),                                         # 回查
    )

    response = await service.create_service_order(
        db, _current(), _request(), "idem-key-0001"
    )

    assert response.matchmaker_id == 21
    insert_params = [params for statement, params in db.calls if "INSERT INTO payment_order" in statement]
    assert insert_params and insert_params[0]["matchmaker_id"] == 21
    assert db.committed is True
