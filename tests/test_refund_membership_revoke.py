"""D-22 回归：会员订单退款必须同步回收 user_membership。

历史缺陷：`refund_order` 只把 `payment_order.status` 改为 3（已退款），
不会回收 `user_membership`，导致用户退款后仍在有效期内可继续使用会员权益。

验收口径（见 docs/全项目后端详细修改方案清单-2026-10-12.md D-22）：
1. `type=1`（会员）订单退款 → 对应 `user_membership` 置为已退款（status=3）并留审计；
2. `type<>1`（牵线/爆灯/活动等）订单退款 → 不触碰 `user_membership`；
3. 无订单号时不得执行空条件更新；
4. 门店账号越权退款仍返回 404（沿用既有逻辑，不被本次改动破坏）。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.schemas.finance import FinanceRefundRequest
from app.services import finance

ORDER_ID = 11
ORDER_NO = "VIP20261012000000ABCDE"


class StubResult:
    def __init__(self, *, rows=None, first=None):
        self._rows = list(rows or [])
        self._first = first

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first


class StubDB:
    def __init__(self, results=None):
        self.statements: list[tuple[str, dict]] = []
        self._results = list(results or [])

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        if self._results:
            return self._results.pop(0)
        return StubResult()

    async def commit(self):
        return None

    def sql(self) -> str:
        return "\n".join(text for text, _ in self.statements)

    def params_of(self, needle: str) -> list[dict]:
        return [params for text, params in self.statements if needle in text]


class _Admin:
    id = 4


def _order(*, order_type: int, status: int = 1, order_no: str | None = ORDER_NO) -> dict:
    return {
        "id": ORDER_ID,
        "status": status,
        "type": order_type,
        "order_no": order_no,
        "service_request_id": None,
    }


def _refund(db: StubDB) -> None:
    asyncio.run(
        finance.refund_order(db, _Admin(), ORDER_ID, FinanceRefundRequest(reason="用户申请退款"))
    )


def test_membership_order_refund_revokes_user_membership() -> None:
    db = StubDB(results=[StubResult(first=_order(order_type=1)), StubResult(rows=[]), StubResult(rows=[]), StubResult(rows=[{"id": 21, "status": 1}]), StubResult(rows=[])])
    _refund(db)
    sql = db.sql()
    assert "UPDATE user_membership SET status = 3" in sql, "会员退款必须回收会员权益"
    revoke_params = db.params_of("UPDATE user_membership SET status = 3")
    assert revoke_params and revoke_params[0]["membership_id"] == 21
    audit_params = db.params_of("membership.refund_revoke")
    assert audit_params and audit_params[0]["order_id"] == ORDER_ID, "会员退款回收须留可追溯审计"


def test_non_membership_order_refund_does_not_touch_membership() -> None:
    db = StubDB(results=[StubResult(first=_order(order_type=3)), StubResult(rows=[]), StubResult(rows=[])])
    _refund(db)
    assert "user_membership" not in db.sql(), "非会员订单退款不得触碰会员表"


def test_membership_refund_without_order_no_is_safe() -> None:
    db = StubDB(
        results=[StubResult(first=_order(order_type=1, order_no=None)), StubResult(rows=[]), StubResult(rows=[])]
    )
    _refund(db)
    assert "UPDATE user_membership" not in db.sql(), "无订单号时不得执行空条件更新"


def test_refund_still_404_when_order_not_found() -> None:
    db = StubDB(results=[StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        _refund(db)
    assert exc.value.status_code == 404
