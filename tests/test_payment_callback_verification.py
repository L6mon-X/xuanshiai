"""D-21 回归：微信支付回调验签、金额一致性、订单归属与幂等。

覆盖方案清单 D-21 的验收口径：
1. 回调必须验签通过才履约；
2. 金额与订单不一致必须拒绝；
3. 重复回调幂等（不重复发放会员）；
4. real 模式缺少验签密钥时 fail-closed（503）；
5. 验签通过但语义异常的拒绝须落业务审计。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import payment_callback_signature
from app.schemas.membership import WechatPaymentCallback
from app.services import membership

MOCK_SECRET = "mock-payment-secret"
ORDER_NO = "VIP20261012000000ABCDE"
TRANSACTION_ID = "wx-txn-0001"
AMOUNT = 99.0


class StubResult:
    def __init__(self, *, first=None, scalar=None):
        self._first = first
        self._scalar = scalar

    def first(self):
        return self._first

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self


class StubDB:
    """记录全部 SQL 的假会话；`begin()` 仅作事务边界占位。"""

    def __init__(self, results=None):
        self.statements: list[tuple[str, dict]] = []
        self._results = list(results or [])
        self.committed = 0

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        if self._results:
            return self._results.pop(0)
        return StubResult()

    @asynccontextmanager
    async def begin(self):
        yield self

    async def commit(self):
        self.committed += 1

    def sql(self) -> str:
        return "\n".join(text for text, _ in self.statements)


def _callback(**overrides) -> WechatPaymentCallback:
    payload = {
        "order_no": ORDER_NO,
        "transaction_id": TRANSACTION_ID,
        "amount": AMOUNT,
        "signature": payment_callback_signature(ORDER_NO, TRANSACTION_ID, AMOUNT, MOCK_SECRET),
    }
    payload.update(overrides)
    return WechatPaymentCallback(**payload)


def _order_row(*, status: int = 0, amount: float = AMOUNT) -> dict:
    return {
        "id": 11,
        "user_id": 7,
        "amount": amount,
        "type": 1,
        "status": status,
        "order_no": ORDER_NO,
        "code": "monthly",
        "duration_days": 30,
    }


# --------------------------------------------------------------------------- #
# 纯函数：签名
# --------------------------------------------------------------------------- #


def test_signature_is_deterministic_and_amount_sensitive() -> None:
    base = payment_callback_signature(ORDER_NO, TRANSACTION_ID, 99.0, MOCK_SECRET)
    assert base == payment_callback_signature(ORDER_NO, TRANSACTION_ID, 99, MOCK_SECRET)
    assert base != payment_callback_signature(ORDER_NO, TRANSACTION_ID, 98.0, MOCK_SECRET)
    assert base != payment_callback_signature(ORDER_NO, "other-txn", 99.0, MOCK_SECRET)
    assert base != payment_callback_signature(ORDER_NO, TRANSACTION_ID, 99.0, "other-secret")


def test_verify_rejects_forged_signature() -> None:
    with pytest.raises(HTTPException) as exc:
        membership.verify_payment_callback(_callback(signature="0" * 64))
    assert exc.value.status_code == 401


def test_verify_accepts_valid_signature() -> None:
    membership.verify_payment_callback(_callback())


def test_real_mode_without_sign_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "wechat_payment_mode", "real")
    monkeypatch.setattr(settings, "wechat_payment_sign_key", None)
    with pytest.raises(HTTPException) as exc:
        membership.verify_payment_callback(_callback())
    assert exc.value.status_code == 503


def test_real_mode_uses_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "wechat_payment_mode", "real")
    monkeypatch.setattr(settings, "wechat_payment_sign_key", SecretStr("real-key"))
    valid = _callback(signature=payment_callback_signature(ORDER_NO, TRANSACTION_ID, AMOUNT, "real-key"))
    with pytest.raises(HTTPException) as exc:
        membership.verify_payment_callback(valid)
    assert exc.value.status_code == 503
    with pytest.raises(HTTPException):
        membership.verify_payment_callback(_callback())


# --------------------------------------------------------------------------- #
# 编排：handle_wechat_callback
# --------------------------------------------------------------------------- #


def test_callback_rejects_forged_signature_before_touching_db() -> None:
    db = StubDB()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(membership.handle_wechat_callback(db, _callback(signature="f" * 64)))
    assert exc.value.status_code == 401
    assert db.statements == [], "验签失败不得访问数据库"


def test_callback_rejects_amount_mismatch_and_audits() -> None:
    db = StubDB(results=[StubResult(first=_order_row(amount=199.0))])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(membership.handle_wechat_callback(db, _callback(amount=AMOUNT)))
    assert exc.value.status_code == 409
    sql = db.sql()
    assert "business_audit_log" in sql, "金额不一致必须落业务审计"
    assert "payment.callback.rejected" in sql
    assert "INSERT INTO user_membership" not in sql, "金额不符不得发放会员"


def test_callback_rejects_unknown_order_and_audits() -> None:
    db = StubDB(results=[StubResult(first=None)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(membership.handle_wechat_callback(db, _callback()))
    assert exc.value.status_code == 404
    assert "payment.callback.rejected" in db.sql()


def test_callback_is_idempotent_on_already_paid_order() -> None:
    db = StubDB(results=[StubResult(first=_order_row(status=1))])
    asyncio.run(membership.handle_wechat_callback(db, _callback()))
    sql = db.sql()
    assert "INSERT INTO user_membership" not in sql, "重复回调不得重复发放会员"
    assert "SET status=1" not in sql, "重复回调不得重复置为已支付"


def test_callback_rejects_non_payable_status() -> None:
    db = StubDB(results=[StubResult(first=_order_row(status=3))])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(membership.handle_wechat_callback(db, _callback()))
    assert exc.value.status_code == 409
    assert "payment.callback.rejected" in db.sql()


def test_callback_pays_and_grants_membership_when_valid() -> None:
    db = StubDB(results=[StubResult(first=_order_row())])
    asyncio.run(membership.handle_wechat_callback(db, _callback()))
    sql = db.sql()
    assert "SET status=1" in sql
    assert "INSERT INTO user_membership" in sql
    assert "business_audit_log" not in sql


def test_real_mode_requires_amount_when_signature_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "wechat_payment_mode", "real")
    monkeypatch.setattr(settings, "wechat_payment_sign_key", SecretStr("real-key"))
    signature = payment_callback_signature(ORDER_NO, TRANSACTION_ID, None, "real-key")
    body = WechatPaymentCallback(order_no=ORDER_NO, transaction_id=TRANSACTION_ID, signature=signature)
    db = StubDB(results=[StubResult(first=_order_row())])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(membership.handle_wechat_callback(db, body))
    assert exc.value.status_code == 503
