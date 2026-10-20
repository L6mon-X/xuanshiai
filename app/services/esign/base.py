"""电子签供应商统一接口。

真实实现（腾讯电子签）需要 SecretId/SecretKey 与联调凭证，未配置时所有动作
必须抛 ``HTTPException(503)``，避免合同被标记为"已发起"却没有真实签署流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EsignFlowResult:
    provider_flow_id: str
    sign_url: str | None = None
    status: str = "signing"
    extra: dict[str, str] = field(default_factory=dict)


class EsignProvider(Protocol):
    """电子签供应商必须实现的接口。"""

    name: str

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
        """发起签署流程。"""

    async def query_flow(self, provider_flow_id: str) -> EsignFlowResult:
        """查询签署状态。"""

    async def void_flow(self, provider_flow_id: str, reason: str) -> None:
        """作废签署流程。"""
