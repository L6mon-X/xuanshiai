"""电子合同（A3）contracts：模板 / 印章 / 合同 / 签署流水 / 配置。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_STATUS = r"^(draft|signing|signed|voided|expired)$"


# ─────────────────────────── 配置 ───────────────────────────


class EcontractConfig(BaseModel):
    """电子签配置：密钥类只回显「是否已配置」。"""

    secret_id_configured: bool
    secret_key_configured: bool
    operator_configured: bool
    configured: bool
    adapter_implemented: bool
    enabled: bool = False
    items: list[dict] = Field(default_factory=list)
    version: int | None = None
    updated_at: datetime | None = None


class EcontractConfigUpdate(BaseModel):
    """只接受非敏感项；SecretId/SecretKey 必须走环境变量，传了会被 422 拒绝。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    items: list[dict] | None = None

    @model_validator(mode="after")
    def require_update(self) -> "EcontractConfigUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


# ─────────────────────────── 模板 ───────────────────────────


class EcontractTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    contract_type: str = Field(default="红娘服务协议", max_length=64)
    provider_template_id: str | None = Field(default=None, max_length=128)
    content: str | None = Field(default=None, max_length=200000)
    file_url: str | None = Field(default=None, max_length=500)
    status: int = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def validate_template(self) -> "EcontractTemplateCreate":
        if not self.content and not self.provider_template_id and not self.file_url:
            raise ValueError("正文、电子签模板 ID、模板文件至少提供一项")
        return self


class EcontractTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contract_type: str | None = Field(default=None, max_length=64)
    provider_template_id: str | None = Field(default=None, max_length=128)
    content: str | None = Field(default=None, max_length=200000)
    file_url: str | None = Field(default=None, max_length=500)
    status: int | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_update(self) -> "EcontractTemplateUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class EcontractTemplateItem(BaseModel):
    id: int
    name: str
    contract_type: str
    provider_template_id: str | None = None
    content: str | None = None
    file_url: str | None = None
    status: int
    usage_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EcontractTemplatePage(BaseModel):
    items: list[EcontractTemplateItem]
    page: int
    page_size: int
    total: int
    has_more: bool


# ─────────────────────────── 印章 ───────────────────────────


class EcontractSealCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    seal_type: str = Field(default="company", pattern="^(company|personal)$")
    image_url: str = Field(min_length=1, max_length=500, description="印章图片（multipart 上传后返回的地址）")
    authorized_person: str | None = Field(default=None, max_length=64)
    provider_seal_id: str | None = Field(default=None, max_length=128)


class EcontractSealUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    seal_type: str | None = Field(default=None, pattern="^(company|personal)$")
    image_url: str | None = Field(default=None, min_length=1, max_length=500)
    authorized_person: str | None = Field(default=None, max_length=64)
    provider_seal_id: str | None = Field(default=None, max_length=128)
    status: int | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_update(self) -> "EcontractSealUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class EcontractSealItem(BaseModel):
    id: int
    name: str
    seal_type: str
    image_url: str
    authorized_person: str | None = None
    provider_seal_id: str | None = None
    status: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ─────────────────────────── 合同 ───────────────────────────


class EcontractCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    template_id: int | None = Field(default=None, ge=1)
    seal_id: int | None = Field(default=None, ge=1)
    contract_type: str | None = Field(default=None, max_length=64)
    member_id: int | None = Field(default=None, ge=1)
    member_name: str | None = Field(default=None, max_length=64)
    member_phone: str | None = Field(default=None, max_length=32)
    amount: float | None = Field(default=None, ge=0)
    content: str | None = Field(default=None, max_length=200000)
    expire_days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def validate_create(self) -> "EcontractCreate":
        if self.member_id is None and not (self.member_name and self.member_phone):
            raise ValueError("member_id 或（member_name + member_phone）至少提供一组")
        return self


class EcontractVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class EcontractEventItem(BaseModel):
    id: int
    event: str
    actor: str | None = None
    detail: str | None = None
    created_at: datetime | None = None


class EcontractItem(BaseModel):
    id: int
    contract_no: str
    template_id: int | None = None
    template_name: str | None = None
    seal_id: int | None = None
    seal_name: str | None = None
    title: str
    contract_type: str
    member_id: int | None = None
    member_name: str | None = None
    member_phone: str | None = None
    amount: float | None = None
    status: str
    provider_flow_id: str | None = None
    sign_url: str | None = None
    signed_at: datetime | None = None
    expire_at: datetime | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EcontractDetail(EcontractItem):
    content: str | None = None
    events: list[EcontractEventItem] = Field(default_factory=list)


class EcontractPage(BaseModel):
    items: list[EcontractItem]
    page: int
    page_size: int
    total: int
    has_more: bool
