"""电话外呼供应商统一接口。

与 ``app/services/sms/base.py`` 同构：路由层只依赖本协议，具体厂商实现
（捷讯等）在凭证齐全后补入 ``providers.py`` 的工厂表。未配置的实现必须抛
``HTTPException(503)``，不得静默返回成功，避免名单被标记为「已呼叫」却没有
真正外呼。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OutboundBalance:
    provider: str
    account_name: str | None
    balance: float
    currency: str = "CNY"


@dataclass(frozen=True)
class OutboundDialResult:
    provider_call_id: str | None = None
    recording_url: str | None = None
    duration: int = 0
    result: str = "connected"
    extra: dict[str, str] = field(default_factory=dict)


class OutboundProvider(Protocol):
    """外呼供应商必须实现的接口。"""

    name: str

    async def fetch_balance(self) -> OutboundBalance:
        """查询账户余额；未配置时抛 503。"""

    async def dial(self, phone: str, *, caller_number: str | None, task_id: int | None) -> OutboundDialResult:
        """发起外呼；未配置时抛 503。"""

    async def fetch_records(self, *, since: str | None, limit: int) -> list[OutboundDialResult]:
        """拉取供应商侧通话记录；未配置时抛 503。"""
