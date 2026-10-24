"""QR code management (二维码管理, A5) contracts for the back office."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class QrcodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scene: str = Field(default="h5", max_length=32, description="场景：h5 落地页 / follow 关注公众号")
    type: str = Field(default="h5", max_length=16, description="编码载体：h5 / miniprogram 小程序码")
    target_url: str = Field(min_length=1, max_length=500, description="指向地址（小程序码为小程序 path）")
    description: str | None = Field(default=None, max_length=500)
    expire_days: int = Field(default=30, ge=1, le=3650, description="有效期天数，生成时折算为 expire_at")

    @model_validator(mode="after")
    def check_scene(self) -> "QrcodeCreate":
        if self.scene not in {"h5", "follow"}:
            raise ValueError("scene 只支持 h5 / follow")
        if self.type not in {"h5", "miniprogram"}:
            raise ValueError("type 只支持 h5 / miniprogram")
        return self


class QrcodeRenew(BaseModel):
    days: int = Field(..., ge=1, le=365, description="续期天数，从 max(now, 当前失效时间) 起算")


class QrcodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_url: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_update(self) -> "QrcodeUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class QrcodeItem(BaseModel):
    id: int
    name: str
    scene: str
    type: str
    target_url: str
    description: str | None = None
    expire_at: datetime
    status: int
    image_url: str
    renew_count: int = 0
    last_renewed_at: datetime | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QrcodePage(BaseModel):
    items: list[QrcodeItem]
    page: int
    page_size: int
    total: int
    has_more: bool
