"""VIP and login-log contracts for member CRM."""

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field, model_validator


class AdminVipItem(BaseModel):
    membership_id: int
    user_id: int
    nickname: str | None
    phone: str | None
    package_type: str | None
    amount: float | None
    order_no: str | None
    start_at: datetime | None
    end_at: datetime | None
    status: int
    open_method: str | None = None
    open_nature: str | None = None
    line_total: int = 0
    line_remaining: int = 0


class AdminVipPage(BaseModel):
    items: list[AdminVipItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class AdminLoginLogItem(BaseModel):
    id: int
    user_id: int
    nickname: str | None
    login_status: int
    ip: str | None
    device_id: str | None
    platform: str | None
    failure_reason: str | None
    created_at: datetime
    # A12 平台用户登录日志全局列表补充：登录方式与手机号（旧逐会员接口不投影时为默认值）。
    login_type: int | None = None
    phone: str | None = None


class AdminLoginLogPage(BaseModel):
    items: list[AdminLoginLogItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class LoginLogDeleteResult(BaseModel):
    """登录日志删除/清空结果（A12）。``deleted`` 为本次实际删除行数。"""

    deleted: int = Field(ge=0)


class AdminVipUpdate(BaseModel):
    action: str = Field(pattern="^(OPEN|RENEW|CANCEL)$")
    package_type: str | None = Field(default=None, min_length=1, max_length=64)
    order_no: str | None = Field(default=None, min_length=8, max_length=64)
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_action(self) -> "AdminVipUpdate":
        if self.action in ("OPEN", "RENEW") and (not self.package_type or not self.order_no):
            raise ValueError("OPEN/RENEW 必须提供 package_type 和 order_no")
        if self.action == "CANCEL" and not self.reason:
            raise ValueError("CANCEL 必须填写 reason")
        return self


class AdminVipUpdateResponse(BaseModel):
    membership_id: int
    user_id: int
    action: str
    package_type: str | None
    status: int
    start_at: datetime | None
    end_at: datetime | None
    order_no: str | None
    reason: str | None


class ImpersonateSessionResponse(BaseModel):
    """A12-模拟登录：后台为目标用户签发的受限短时只读会话。

    read_only 恒为 True；access_token 只能执行安全方法（GET/HEAD/OPTIONS），
    写方法会被 app/main.py 只读中间件拒绝；expires_in 为秒，到期自动失效。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    impersonated_user_id: int
    session_id: int
    read_only: bool = True
    impersonated_by: int
