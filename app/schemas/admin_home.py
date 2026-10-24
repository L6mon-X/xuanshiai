"""Contracts for the tenant-scoped administrator home page."""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class LegacyResponse(BaseModel, Generic[T]):
    code: int = 200
    data: T
    msg: str = "success"
    success: bool = True


class HomeOperator(BaseModel):
    id: int
    account: str
    name: str
    permissions: list[str]
    locked: bool = False


class HomeAuthorization(BaseModel):
    status: str = "active"
    expires_at: datetime | None = None
    sms_remaining_count: int = Field(default=0, ge=0)


class SmsStatistics(BaseModel):
    success_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    remaining_count: int = Field(default=0, ge=0)


class HomeHeader(BaseModel):
    has_unread_feedback: bool = False
    unread_announcement_count: int = Field(default=0, ge=0)
    sms: SmsStatistics


class AdminBootstrap(BaseModel):
    operator: HomeOperator
    authorization: HomeAuthorization
    header: HomeHeader


class DashboardMetrics(BaseModel):
    member_count: int = Field(default=0, ge=0)
    platform_user_count: int = Field(default=0, ge=0)
    wechat_fan_count: int = Field(default=0, ge=0)
    online_days: int = Field(default=0, ge=0)
    lead_count: int = Field(default=0, ge=0)
    customer_lead_count: int = Field(default=0, ge=0)
    vip_count: int = Field(default=0, ge=0)
    online_vip_count: int = Field(default=0, ge=0)
    offline_vip_count: int = Field(default=0, ge=0)
    matchmaker_count: int = Field(default=0, ge=0)
    service_matchmaker_count: int = Field(default=0, ge=0)
    promotion_matchmaker_count: int = Field(default=0, ge=0)
    successful_match_count: int = Field(default=0, ge=0)
    male_member_count: int = Field(default=0, ge=0)
    female_member_count: int = Field(default=0, ge=0)
    pending_withdrawal_count: int = Field(default=0, ge=0)
    online_income: Decimal = Decimal("0.00")
    offline_income: Decimal = Decimal("0.00")


class DashboardPending(BaseModel):
    withdrawal: int = Field(default=0, ge=0)
    matchmaker_application: int = Field(default=0, ge=0)
    matchmaker_service: int = Field(default=0, ge=0)
    match_application: int = Field(default=0, ge=0)
    report: int = Field(default=0, ge=0)


class DashboardGender(BaseModel):
    male: int = Field(default=0, ge=0)
    female: int = Field(default=0, ge=0)
    unspecified: int = Field(default=0, ge=0)


class IncomeRankItem(BaseModel):
    product_type: str
    income: Decimal = Decimal("0.00")
    proportion: Decimal = Decimal("0.00")


class DailyTrend(BaseModel):
    date: date
    member_count: int = Field(default=0, ge=0)
    lead_count: int = Field(default=0, ge=0)
    paid_count: int = Field(default=0, ge=0)
    completed_refund_count: int = Field(default=0, ge=0)
    paid_amount: Decimal = Decimal("0.00")
    online_paid_amount: Decimal = Decimal("0.00")
    offline_paid_amount: Decimal = Decimal("0.00")
    completed_refund_amount: Decimal = Decimal("0.00")
    net_amount: Decimal = Decimal("0.00")


class AdminDashboard(BaseModel):
    from_date: date
    to_date: date
    metrics: DashboardMetrics
    pending: DashboardPending = Field(default_factory=DashboardPending)
    member_gender: DashboardGender = Field(default_factory=DashboardGender)
    income_rank: list[IncomeRankItem] = Field(default_factory=list)
    trends: list[DailyTrend]


class DashboardHonor(BaseModel):
    """光荣榜聚合（A11，近似口径只读）。

    口径说明（本轮「近似口径优先」）：
    - ``line_total`` / ``line_success`` 取线上牵线记录 ``match_apply`` 总数 / 成功数（status=1）；
    - ``meeting_arranged`` 取线下约见 ``meeting_record`` 已安排总数；
    - ``activity_held`` 原站口径为「已举办场次」，本库无场次统计，按用户确认用**活动总数**近似；
    - ``no_single`` 原站为「脱单人数」，本库无独立字段，近似取「牵线成功涉及的去重会员数」。
    """

    line_total: int = Field(default=0, ge=0)
    line_success: int = Field(default=0, ge=0)
    meeting_arranged: int = Field(default=0, ge=0)
    activity_held: int = Field(default=0, ge=0)
    no_single: int = Field(default=0, ge=0)


class DashboardMonthlyDelta(BaseModel):
    """统计卡「本月 +X」增量（A11，只读，按 created_at/start_at 落在自然月内计数）。

    原站「公众号粉丝 / 红娘团队」两项无月增量来源恒显示 +0；本接口用现有表
    （users.openid / user_matchmaker_apply）近似给出真实月增量，不减损信息。
    """

    month: str
    member_delta: int = Field(default=0, ge=0)
    platform_user_delta: int = Field(default=0, ge=0)
    wechat_fan_delta: int = Field(default=0, ge=0)
    lead_delta: int = Field(default=0, ge=0)
    vip_delta: int = Field(default=0, ge=0)
    online_vip_delta: int = Field(default=0, ge=0)
    offline_vip_delta: int = Field(default=0, ge=0)
    matchmaker_delta: int = Field(default=0, ge=0)


class AnnouncementItem(BaseModel):
    id: int
    version_id: int | None = None
    category: str
    title: str
    title_color: str | None = None
    title_bold: bool = False
    top: bool = False
    sort_order: int = 0
    link_to: str | None = None
    created_at: datetime
    read: bool = False


class AnnouncementPage(BaseModel):
    items: list[AnnouncementItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class AcademyCategory(BaseModel):
    id: int
    parent_id: int | None = None
    name: str
    description: str | None = None
    image: str | None = None
    category_type: str = "Guides"
    sort: int = 0
    enabled: bool = True
    matchmaker_class_enabled: bool = False
    children: list["AcademyCategory"] = Field(default_factory=list)


class RechargeItem(BaseModel):
    id: int
    name: str
    resource_type: str
    quantity: int = Field(ge=1)
    price: Decimal
