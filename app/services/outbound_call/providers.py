"""外呼供应商实现与工厂。"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings
from app.services.outbound_call.base import OutboundBalance, OutboundDialResult, OutboundProvider


class DisabledOutboundProvider:
    """未配置外呼平台时的实现：所有动作 fail-closed。"""

    name = "disabled"

    async def fetch_balance(self) -> OutboundBalance:
        raise HTTPException(status_code=503, detail="外呼平台未配置")

    async def dial(
        self, phone: str, *, caller_number: str | None, task_id: int | None
    ) -> OutboundDialResult:
        raise HTTPException(status_code=503, detail="外呼平台未配置")

    async def fetch_records(self, *, since: str | None, limit: int) -> list[OutboundDialResult]:
        raise HTTPException(status_code=503, detail="外呼平台未配置")


class MockOutboundProvider:
    """仅用于 development/testing：不发起真实外呼，返回可对账的假通话。"""

    name = "mock"

    def _guard(self) -> None:
        if not settings.is_test_mode:
            raise HTTPException(status_code=503, detail="外呼 Mock 服务仅允许测试环境使用")

    async def fetch_balance(self) -> OutboundBalance:
        self._guard()
        return OutboundBalance(
            provider="mock",
            account_name=settings.outbound_call_account or "mock-account",
            balance=1000.0,
        )

    async def dial(
        self, phone: str, *, caller_number: str | None, task_id: int | None
    ) -> OutboundDialResult:
        self._guard()
        if not phone:
            raise HTTPException(status_code=422, detail="被叫号码为空")
        return OutboundDialResult(
            provider_call_id=f"mock-{phone[-4:]}-{task_id or 0}",
            duration=30,
            result="connected",
        )

    async def fetch_records(self, *, since: str | None, limit: int) -> list[OutboundDialResult]:
        self._guard()
        return []


def get_outbound_provider() -> OutboundProvider:
    """按 ``outbound_call_provider`` 返回外呼供应商；未实现的值一律 503。"""
    providers: dict[str, OutboundProvider] = {
        "disabled": DisabledOutboundProvider(),
        "mock": MockOutboundProvider(),
    }
    provider = providers.get(settings.outbound_call_provider.lower())
    if provider is None:
        raise HTTPException(status_code=503, detail="外呼平台供应商未实现")
    return provider


def provider_status() -> dict[str, object]:
    """返回供应商可用性（不含任何密钥），供 ``GET /admin/outbound-call/config`` 回显。"""
    provider = settings.outbound_call_provider.lower()
    configured = provider not in {"", "disabled"} and bool(
        settings.outbound_call_base_url and settings.outbound_call_account
    )
    return {
        "provider": provider,
        "configured": configured,
        "base_url_configured": bool(settings.outbound_call_base_url),
        "account_configured": bool(settings.outbound_call_account),
        "secret_configured": settings.outbound_call_secret is not None,
    }
