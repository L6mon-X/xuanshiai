"""Lovecard templates (相亲卡, A8) contracts for the back office."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class LovecardTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    style: int = Field(default=1, ge=1, le=25, description="卡片样式编号 1–25")
    activity_id: int | None = Field(default=None, ge=1, description="关联线下活动 offline_activity.id")
    register_start: datetime | None = None
    register_end: datetime | None = None
    region_code: str | None = Field(default=None, max_length=64)
    native_place: str | None = Field(default=None, max_length=64)
    height_min: int | None = Field(default=None, ge=0, le=300)
    height_max: int | None = Field(default=None, ge=0, le=300)
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    promoter_id: int | None = Field(default=None, ge=1, description="推广红娘（users.id）")
    matchmaker_id: int | None = Field(default=None, ge=1, description="服务红娘（users.id）")
    qrcode_desc: str | None = Field(default=None, max_length=500)
    qrcode_expire_days: int | None = Field(default=None, ge=1, le=3650, description="卡片二维码有效期（天）")
    limit_latest: int = Field(default=5, ge=1, le=200, description="按模板条件取前 N 条会员生成")
    tags: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_ranges(self) -> "LovecardTemplateBase":
        if self.register_start and self.register_end and self.register_end <= self.register_start:
            raise ValueError("register_end 必须晚于 register_start")
        if self.height_min is not None and self.height_max is not None and self.height_max < self.height_min:
            raise ValueError("height_max 不能小于 height_min")
        if self.age_min is not None and self.age_max is not None and self.age_max < self.age_min:
            raise ValueError("age_max 不能小于 age_min")
        return self


class LovecardTemplateCreate(LovecardTemplateBase):
    pass


class LovecardTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    style: int | None = Field(default=None, ge=1, le=25)
    activity_id: int | None = Field(default=None, ge=1)
    register_start: datetime | None = None
    register_end: datetime | None = None
    region_code: str | None = Field(default=None, max_length=64)
    native_place: str | None = Field(default=None, max_length=64)
    height_min: int | None = Field(default=None, ge=0, le=300)
    height_max: int | None = Field(default=None, ge=0, le=300)
    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    promoter_id: int | None = Field(default=None, ge=1)
    matchmaker_id: int | None = Field(default=None, ge=1)
    qrcode_desc: str | None = Field(default=None, max_length=500)
    qrcode_expire_days: int | None = Field(default=None, ge=1, le=3650)
    limit_latest: int | None = Field(default=None, ge=1, le=200)
    tags: list[str] | None = Field(default=None, max_length=50)
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "LovecardTemplateUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class LovecardTemplateItem(BaseModel):
    id: int
    name: str
    style: int = 1
    activity_id: int | None = None
    register_start: datetime | None = None
    register_end: datetime | None = None
    region_code: str | None = None
    native_place: str | None = None
    height_min: int | None = None
    height_max: int | None = None
    age_min: int | None = None
    age_max: int | None = None
    promoter_id: int | None = None
    matchmaker_id: int | None = None
    qrcode_desc: str | None = None
    qrcode_expire_days: int | None = None
    limit_latest: int = 5
    tags: list[str] = []
    enabled: bool = True
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LovecardTemplatePage(BaseModel):
    items: list[LovecardTemplateItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class LovecardGenerateRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=200, description="本次生成数量上限，缺省取模板 limit_latest")


class LovecardGenerateResult(BaseModel):
    template_id: int
    batch_no: str
    generated: int
    images: list[str]  # 现签 URL 列表，与 generation 行一一对应
    failures: list[dict]  # [{user_id, error}]


class LovecardGenerationItem(BaseModel):
    id: int
    template_id: int
    batch_no: str | None = None
    user_id: int
    nickname: str | None = None
    image_url: str | None = None
    status: str
    error: str | None = None
    generated_by: int | None = None
    created_at: datetime | None = None


class LovecardGenerationPage(BaseModel):
    items: list[LovecardGenerationItem]
    page: int
    page_size: int
    total: int
    has_more: bool
