"""短信服务统一接口。"""

from typing import Protocol


class SmsProvider(Protocol):
    """短信供应商必须实现的接口。"""

    name: str

    async def send_code(self, phone: str, purpose: str, code: str) -> None:
        """发送验证码；失败时抛出异常。"""

    async def send_template(
        self, phone: str, template_code: str, params: dict[str, str]
    ) -> str | None:
        """发送模板短信，返回供应商流水号（可用于发送记录对账）。

        未配置的实现必须抛 ``HTTPException(503)``，不得静默成功。
        """
