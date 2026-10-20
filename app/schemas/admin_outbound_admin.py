"""外呼（A6）contracts：平台配置、余额、外显号码、外呼名单、通话记录。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────── 配置与余额 ───────────────────────────


class OutboundConfig(BaseModel):
    """平台配置：只回显非敏感项与「是否已配置」，密钥一律不回显。"""

    provider: str
    configured: bool
    base_url_configured: bool
    account_configured: bool
    secret_configured: bool
    account_name: str | None = None
    call_center_url: str | None = None
    record_download_url: str | None = None
    version: int | None = None
    updated_at: datetime | None = None


class OutboundConfigUpdate(BaseModel):
    """非敏感配置项；密钥/账号密码类字段必须在 .env 注入，传了会被 422 拒绝。"""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=32)
    account_name: str | None = Field(default=None, max_length=128)
    call_center_url: str | None = Field(default=None, max_length=500)
    record_download_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_update(self) -> "OutboundConfigUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class OutboundBalanceItem(BaseModel):
    provider: str
    account_name: str | None = None
    balance: float = 0.0
    currency: str = "CNY"
    checked_at: datetime | None = None


# ─────────────────────────── 外显号码 ───────────────────────────


class OutboundNumberCreate(BaseModel):
    phone: str = Field(min_length=5, max_length=32, description="外显号码")
    area: str | None = Field(default=None, max_length=64)
    bound_matchmaker_id: int | None = Field(default=None, ge=1)
    remark: str | None = Field(default=None, max_length=255)


class OutboundNumberUpdate(BaseModel):
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    area: str | None = Field(default=None, max_length=64)
    status: int | None = Field(default=None, ge=0, le=1)
    bound_matchmaker_id: int | None = Field(default=None, ge=1)
    remark: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_update(self) -> "OutboundNumberUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class OutboundNumberItem(BaseModel):
    id: int
    phone: str
    area: str | None = None
    status: int
    bound_matchmaker_id: int | None = None
    bound_matchmaker_name: str | None = None
    remark: str | None = None
    created_at: datetime | None = None


class OutboundNumberPage(BaseModel):
    items: list[OutboundNumberItem]
    page: int
    page_size: int
    total: int
    has_more: bool


# ─────────────────────────── 外呼名单 ───────────────────────────


class OutboundTaskItem(BaseModel):
    id: int
    batch_no: str
    member_id: int | None = None
    name: str | None = None
    phone: str
    matchmaker_id: int | None = None
    matchmaker_name: str | None = None
    status: str
    result: str | None = None
    remark: str | None = None
    call_count: int = 0
    last_called_at: datetime | None = None
    created_at: datetime | None = None


class OutboundTaskPage(BaseModel):
    items: list[OutboundTaskItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class OutboundTaskImportResult(BaseModel):
    batch_no: str
    total: int
    created: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)


class OutboundTaskCall(BaseModel):
    """单条外呼：号码取名单行，外显号码取号码池或请求指定。"""

    caller_number: str | None = Field(default=None, min_length=5, max_length=32)


# ─────────────────────────── 通话记录 ───────────────────────────


class OutboundRecordItem(BaseModel):
    id: int
    task_id: int | None = None
    phone: str
    matchmaker_id: int | None = None
    matchmaker_name: str | None = None
    direction: str
    result: str | None = None
    duration: int = 0
    recording_url: str | None = None
    provider_call_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None


class OutboundRecordPage(BaseModel):
    items: list[OutboundRecordItem]
    page: int
    page_size: int
    total: int
    has_more: bool
