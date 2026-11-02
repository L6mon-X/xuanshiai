"""微信支付对账：账单类型映射回归。

微信 ``/v3/bill/tradebill`` 的 ``bill_type`` 只接受 ALL / SUCCESS / REFUND；
数据库 ``payment_reconcile_batch.bill_type`` 仍使用内部标签 TRADE。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.services.payment.base import PaymentAPIError
from app.services.payment.reconcile import ReconcileService


class _StubResult:
    def mappings(self):
        return self

    def first(self):
        return None


class _StubDB:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        return _StubResult()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    @asynccontextmanager
    async def begin(self):
        yield self


class _RecordingGateway:
    def __init__(self) -> None:
        self.bill_types: list[str] = []

    async def get_bill_download_url(self, bill_date: str, bill_type: str = "ALL") -> str:
        self.bill_types.append(bill_type)
        raise PaymentAPIError(400, "stop after recording")


class _MissingBillGateway:
    async def get_bill_download_url(self, bill_date: str, bill_type: str = "ALL") -> str:
        raise PaymentAPIError(400, "请求的账单文件不存在", code="BILL_NOT_EXIST")


def test_reconcile_passes_wechat_enum_not_internal_label() -> None:
    gateway = _RecordingGateway()
    db = _StubDB()
    service = ReconcileService(gateway)  # type: ignore[arg-type]

    with pytest.raises(PaymentAPIError):
        asyncio.run(service.download_and_reconcile_bill(db, "2026-11-01"))

    assert gateway.bill_types == ["ALL"]


def test_reconcile_failure_batch_keeps_internal_trade_label() -> None:
    gateway = _RecordingGateway()
    db = _StubDB()
    service = ReconcileService(gateway)  # type: ignore[arg-type]

    with pytest.raises(PaymentAPIError):
        asyncio.run(service.download_and_reconcile_bill(db, "2026-11-01"))

    batch_inserts = [params for sql, params in db.statements if "payment_reconcile_batch" in sql]
    assert batch_inserts, "失败批次应写 payment_reconcile_batch"
    assert batch_inserts[-1]["bill_type"] == "TRADE"


def test_reconcile_missing_bill_records_empty_batch() -> None:
    db = _StubDB()
    service = ReconcileService(_MissingBillGateway())  # type: ignore[arg-type]

    result = asyncio.run(service.download_and_reconcile_bill(db, "2026-11-01"))

    assert result == {
        "bill_date": "2026-11-01",
        "batch_id": None,
        "record_count": 0,
        "diff_count": 0,
        "status": "EMPTY",
    }
    batch_statements = [
        (sql, params) for sql, params in db.statements if "payment_reconcile_batch" in sql
    ]
    assert batch_statements, "无账单日应写 payment_reconcile_batch"
    assert batch_statements[-1][1]["bill_type"] == "TRADE"
    assert "EMPTY" in batch_statements[-1][0]
