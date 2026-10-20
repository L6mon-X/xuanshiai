"""Member-side abandonment (会员弃海, A9/B3) contracts for the back office."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.matchmaker_crm_admin import MemberListItem


class AbandonedMemberItem(MemberListItem):
    """弃海会员行：复用会员列表结构，补弃海维度字段。"""

    abandoned_at: datetime
    abandoned_reason: str
    abandon_type: str = "manual"
    abandoned_by: int | None = None


class AbandonedMemberPage(BaseModel):
    items: list[AbandonedMemberItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class MemberAbandonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    abandon_type: Literal["manual", "lead_sync", "auto"] = "manual"


class MemberRestoreRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    matchmaker_id: int | None = Field(default=None, ge=1, description="捞回后分派的服务红娘（users.id）")


class MemberAbandonmentItem(BaseModel):
    id: int
    user_id: int
    nickname: str | None = None
    reason: str
    abandon_type: str
    abandoned_by: int
    abandoned_at: datetime
    restored_by: int | None = None
    restored_at: datetime | None = None
    restore_reason: str | None = None
    assigned_matchmaker_id: int | None = None


class MemberAbandonmentPage(BaseModel):
    items: list[MemberAbandonmentItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class MemberAbandonmentFilter(BaseModel):
    """弃海记录筛选（供文档与内部校验共用）。"""

    abandon_type: Literal["manual", "lead_sync", "auto"] | None = None

    @model_validator(mode="after")
    def noop(self) -> "MemberAbandonmentFilter":
        return self
