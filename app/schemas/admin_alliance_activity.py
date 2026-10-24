"""Alliance activities (活动联盟, A10) contracts for the back office."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AllianceActivityBase(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    cover: str | None = Field(default=None, max_length=500)
    store_id: int | None = Field(default=None, ge=1, description="主办门店 organization.id")
    start_time: datetime
    end_time: datetime
    address: str | None = Field(default=None, max_length=255)
    fee: float = Field(default=0, ge=0, le=1000000)
    capacity: int = Field(default=0, ge=0, le=1000000, description="人数上限，0 不限制")
    intro: str | None = Field(default=None, max_length=20000)
    status: int = Field(default=1, ge=1, le=4, description="1报名中 2已结束 3已取消 4草稿")
    sort: int = Field(default=0, ge=-1000000, le=1000000)

    @model_validator(mode="after")
    def validate_times(self) -> "AllianceActivityBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time 必须晚于 start_time")
        return self


class AllianceActivityCreate(AllianceActivityBase):
    pass


class AllianceActivityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    cover: str | None = Field(default=None, max_length=500)
    store_id: int | None = Field(default=None, ge=1)
    start_time: datetime | None = None
    end_time: datetime | None = None
    address: str | None = Field(default=None, max_length=255)
    fee: float | None = Field(default=None, ge=0, le=1000000)
    capacity: int | None = Field(default=None, ge=0, le=1000000)
    intro: str | None = Field(default=None, max_length=20000)
    status: int | None = Field(default=None, ge=1, le=4)
    sort: int | None = Field(default=None, ge=-1000000, le=1000000)

    @model_validator(mode="after")
    def require_update(self) -> "AllianceActivityUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少提供一个需要修改的字段")
        return self


class AllianceActivityItem(AllianceActivityBase):
    id: int
    store_name: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AllianceActivityPage(BaseModel):
    items: list[AllianceActivityItem]
    page: int
    page_size: int
    total: int
    has_more: bool
