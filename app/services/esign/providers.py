"""电子签供应商实现与工厂。"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings
from app.services.esign.base import EsignFlowResult, EsignProvider


class DisabledEsignProvider:
    """未配置电子签凭据时的实现：所有动作 fail-closed。"""

    name = "disabled"

    async def create_flow(
        self,
        *,
        contract_no: str,
        title: str,
        content: str,
        member_name: str | None,
        member_phone: str | None,
        template_id: str | None,
        seal_id: str | None,
        expire_at: object | None,
    ) -> EsignFlowResult:
        raise HTTPException(status_code=503, detail="电子签服务未配置")

    async def query_flow(self, provider_flow_id: str) -> EsignFlowResult:
        raise HTTPException(status_code=503, detail="电子签服务未配置")

    async def void_flow(self, provider_flow_id: str, reason: str) -> None:
        raise HTTPException(status_code=503, detail="电子签服务未配置")


class MockEsignProvider:
    """仅 development/testing：返回可对账的假流程，不发起真实签署。"""

    name = "mock"

    def _guard(self) -> None:
        if not settings.is_test_mode:
            raise HTTPException(status_code=503, detail="电子签 Mock 服务仅允许测试环境使用")

    async def create_flow(
        self,
        *,
        contract_no: str,
        title: str,
        content: str,
        member_name: str | None,
        member_phone: str | None,
        template_id: str | None,
        seal_id: str | None,
        expire_at: object | None,
    ) -> EsignFlowResult:
        self._guard()
        return EsignFlowResult(
            provider_flow_id=f"mock-flow-{contract_no}",
            sign_url=f"https://mock.esign.local/sign/{contract_no}",
            status="signing",
        )

    async def query_flow(self, provider_flow_id: str) -> EsignFlowResult:
        self._guard()
        return EsignFlowResult(provider_flow_id=provider_flow_id, status="signing")

    async def void_flow(self, provider_flow_id: str, reason: str) -> None:
        self._guard()


def get_esign_provider() -> EsignProvider:
    """按 ``tencent_esign_secret_id`` / ``_secret_key`` 是否齐备返回供应商。

    腾讯电子签真实实现需与厂商联调（见 ``docs/待完成事项.md``），
    当前只有 disabled / mock 两种实现，其余配置值一律 503。
    """
    if settings.is_test_mode:
        return MockEsignProvider()
    return DisabledEsignProvider()


def provider_status() -> dict[str, object]:
    """凭据就绪情况（只回显布尔，密钥绝不外泄）。"""
    secret_ready = (
        settings.tencent_esign_secret_key is not None
        and bool(settings.tencent_esign_secret_key.get_secret_value())
    )
    return {
        "secret_id_configured": bool(settings.tencent_esign_secret_id),
        "secret_key_configured": secret_ready,
        "operator_configured": bool(settings.tencent_esign_operator_open_id),
        "configured": bool(settings.tencent_esign_secret_id) and secret_ready,
        "adapter_implemented": False,
    }
