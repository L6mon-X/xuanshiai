"""Sales library (销售话术库, A7) contracts for the back office."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────── 分类 ───────────────────────────


class SalesCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sort: int = Field(default=0, ge=0, le=100000)
    enabled: bool = True


class SalesCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    sort: int | None = Field(default=None, ge=0, le=100000)
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "SalesCategoryUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class SalesCategoryItem(BaseModel):
    id: int
    name: str
    sort: int = 0
    enabled: bool = True
    item_count: int = 0
    created_at: datetime | None = None


class SalesCategoryPage(BaseModel):
    items: list[SalesCategoryItem]
    page: int
    page_size: int
    total: int
    has_more: bool


# ─────────────────────────── 话术条目 ───────────────────────────


class SalesItemCreate(BaseModel):
    category_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=20000)
    media_url: str | None = Field(default=None, max_length=500, description="配套素材（图片/语音）相对路径，可空")
    pick_limit: int = Field(default=0, ge=0, le=10000, description="每日可取用次数上限，0 不限制")
    sort: int = Field(default=0, ge=0, le=100000)


class SalesItemUpdate(BaseModel):
    category_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=128)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    media_url: str | None = Field(default=None, max_length=500)
    pick_limit: int | None = Field(default=None, ge=0, le=10000)
    status: int | None = Field(default=None, ge=0, le=1)
    sort: int | None = Field(default=None, ge=0, le=100000)

    @model_validator(mode="after")
    def require_update(self) -> "SalesItemUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class SalesItemItem(BaseModel):
    id: int
    category_id: int
    category_name: str | None = None
    title: str
    content: str
    media_url: str | None = None
    pick_limit: int = 0
    status: int = 1
    sort: int = 0
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SalesItemPage(BaseModel):
    items: list[SalesItemItem]
    page: int
    page_size: int
    total: int
    has_more: bool


# ─────────────────────────── 下发 ───────────────────────────


class SalesItemPush(BaseModel):
    matchmaker_ids: list[int] = Field(min_length=1, max_length=200, description="有效服务红娘（users.id）")
    note: str | None = Field(default=None, max_length=500)


class SalesItemPushResult(BaseModel):
    item_id: int
    pushed: list[int]
    skipped: list[dict]  # [{matchmaker_id, reason}]


class SalesPushRecordItem(BaseModel):
    id: int
    item_id: int
    item_title: str | None = None
    matchmaker_id: int
    matchmaker_name: str | None = None
    note: str | None = None
    pushed_by: int
    created_at: datetime | None = None


class SalesPushRecordPage(BaseModel):
    items: list[SalesPushRecordItem]
    page: int
    page_size: int
    total: int
    has_more: bool
