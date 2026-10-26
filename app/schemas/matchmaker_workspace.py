"""Contracts for the mobile service-matchmaker workspace.

The routes in this module deliberately use the normal mobile user session.  They
are not aliases for the independent ``/admin`` matchmaker console.
"""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


WorkspaceLevel = Literal["NORMAL", "SUPER"]
WorkspaceScope = Literal["SELF", "ORGANIZATION"]
ReviewStatus = Literal["PENDING", "PASSED", "REJECTED"]
LeadStatus = Literal["NEW", "CONTACTED", "INTENDED", "CONVERTED", "LOST", "CLOSED"]
FollowUpMethod = Literal["PHONE", "WECHAT", "VISIT", "OTHER"]
IntroductionStatus = Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]


class MatchmakerWorkspaceAccess(BaseModel):
    can_access: bool
    role_status: Literal["active", "inactive"]
    payment_status: Literal["not_required"] = "not_required"
    scope: WorkspaceScope | None = None
    message: str


class MatchmakerWorkspaceProfile(BaseModel):
    user_id: int
    display_name: str
    level: WorkspaceLevel
    scope: WorkspaceScope
    organization_id: int | None


class MatchmakerWorkspaceProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)


class MatchmakerHomepageCase(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    images: list[str] = Field(default_factory=list, max_length=3)


class MatchmakerHomepage(BaseModel):
    """红娘本人可见的主页编辑资料；字段与公开主页同源，落库在入驻申请表。"""

    user_id: int
    nickname: str
    avatar: str | None
    slogan: str | None
    specialties: list[str]
    introduction: str
    success_cases: list[MatchmakerHomepageCase]


class MatchmakerHomepageUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    slogan: str | None = Field(default=None, max_length=64)
    specialties: list[str] | None = Field(default=None, max_length=5)
    introduction: str | None = Field(default=None, min_length=10, max_length=2000)
    success_cases: list[MatchmakerHomepageCase] | None = Field(default=None, max_length=3)

    @field_validator("nickname", "introduction")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("内容不能为空")
        return cleaned

    @field_validator("slogan")
    @classmethod
    def normalize_slogan(cls, value: str | None) -> str | None:
        # 空串表示清空签名，与「未填」在主页上是同一种展示。
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("specialties")
    @classmethod
    def validate_specialties(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("擅长领域不能重复")
        return cleaned

    @field_validator("success_cases")
    @classmethod
    def validate_success_cases(
        cls, value: list[MatchmakerHomepageCase] | None
    ) -> list[MatchmakerHomepageCase] | None:
        if value is None:
            return None
        return [
            case.model_copy(
                update={"description": case.description.strip(), "images": [image.strip() for image in case.images if image.strip()]}
            )
            for case in value
        ]


class WorkspaceMetric(BaseModel):
    key: str
    label: str
    value: str
    action: str
    value_prefix: str | None = Field(default=None, max_length=8)
    badge: str | None = Field(default=None, max_length=32)


class MatchmakerWorkspaceIdentity(BaseModel):
    greeting: str
    name: str
    role_name: str


class MatchmakerWorkspaceDashboard(BaseModel):
    identity: MatchmakerWorkspaceIdentity
    store_metrics: list[WorkspaceMetric] = Field(min_length=8, max_length=8)


def _strip_contact(value: str | None) -> str | None:
    """联系方式归一化：去首尾空白，空串视为未提供（None）。"""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


class WorkspaceLeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    real_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    wechat: str | None = Field(default=None, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    intention_level: Literal[1, 2, 3] = 1
    remark: str | None = Field(default=None, max_length=2000)
    photo: str | None = Field(default=None, max_length=512)
    gender: Literal[1, 2] | None = None
    birthday: date | None = None

    @field_validator("phone", "wechat", mode="before")
    @classmethod
    def normalize_contact(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_contact(value)
        return value

    @model_validator(mode="after")
    def require_phone(self) -> "WorkspaceLeadCreate":
        # 业务口径：线索必须能联系到人，且只有手机号能一键入库成会员（微信号只是文本备注）。
        if not self.phone:
            raise ValueError("必须登记 11 位手机号")
        return self


class WorkspaceLeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    real_name: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    wechat: str | None = Field(default=None, max_length=128)
    intention_level: Literal[1, 2, 3] | None = None
    status: LeadStatus | None = None
    remark: str | None = Field(default=None, max_length=2000)
    next_follow_at: datetime | None = None
    photo: str | None = Field(default=None, max_length=512)
    gender: Literal[1, 2] | None = None
    birthday: date | None = None

    @field_validator("phone", "wechat", mode="before")
    @classmethod
    def normalize_contact(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_contact(value)
        return value

    @model_validator(mode="after")
    def require_update(self) -> "WorkspaceLeadUpdate":
        # 显式传 phone=null/"" 会被归一化成 None：那等于把线索改成联系不上人的死数据。
        if "phone" in self.model_fields_set and not self.phone:
            raise ValueError("手机号不能清空，只能改成有效的 11 位手机号")
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要修改的字段")
        return self


class WorkspaceLead(BaseModel):
    id: int
    name: str
    real_name: str | None = None
    phone: str | None
    wechat: str | None
    source: str
    intention_level: Literal[1, 2, 3]
    status: LeadStatus
    next_follow_at: datetime | None
    created_at: datetime
    updated_at: datetime
    matchmaker_id: int | None = None
    matchmaker_name: str | None = None
    remark: str | None = None
    last_follow_up_at: datetime | None = None
    converted_user_id: int | None = None
    photo: str | None = None
    gender: int | None = None
    birthday: date | None = None


class WorkspaceLeadPage(BaseModel):
    items: list[WorkspaceLead]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceLeadFollowUpCreate(BaseModel):
    method: FollowUpMethod
    content: str = Field(min_length=1, max_length=2000)
    intention_level: Literal[1, 2, 3] | None = None
    next_follow_at: datetime | None = None


class WorkspaceLeadFollowUp(BaseModel):
    id: int
    lead_id: int
    method: FollowUpMethod
    content: str
    intention_level: Literal[1, 2, 3] | None
    next_follow_at: datetime | None
    created_at: datetime


class WorkspaceLeadFollowUpPage(BaseModel):
    items: list[WorkspaceLeadFollowUp]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceAbandonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class WorkspaceAssignRequest(BaseModel):
    """把客源线索分派给同组织内的另一位服务红娘跟进。"""

    matchmaker_id: int = Field(ge=1)


class WorkspaceLeadConvertRequest(BaseModel):
    """一键入库：客源线索转为平台正式用户并进入公开资料审核队列。"""

    gender: Literal[1, 2] | None = None
    remark: str | None = Field(default=None, max_length=500)


class WorkspaceLeadConvertResult(BaseModel):
    lead: "WorkspaceLead"
    user_id: int
    review_status: ReviewStatus = "PENDING"


class WorkspaceLeadFollower(BaseModel):
    """同组织内可被分派跟进线索的服务红娘。"""

    user_id: int
    display_name: str
    is_self: bool = False


class WorkspaceMember(BaseModel):
    user_id: int
    nickname: str
    avatar: str | None
    gender: Literal[1, 2] | None
    birthday: date | None
    hometown: str | None
    residence: str | None
    education: str | None
    job: str | None
    is_married: int | None = None
    height: int | None = None
    realname_status: int | None = None
    matchmaker_id: int | None = None
    matchmaker_name: str | None = None
    profile_completion_score: float
    review_status: ReviewStatus
    review_reason: str | None
    reviewed_at: datetime | None
    next_follow_at: datetime | None
    created_at: datetime


class WorkspaceMemberPage(BaseModel):
    items: list[WorkspaceMember]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceMemberReviewUpdate(BaseModel):
    status: Literal["PASSED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "WorkspaceMemberReviewUpdate":
        if self.status == "REJECTED" and not self.reason:
            raise ValueError("驳回资料时必须填写原因")
        return self


class WorkspaceMemberMatchmakerUpdate(BaseModel):
    """修改会员的跟进服务红娘；置 null 表示改为待分派。"""

    matchmaker_id: int | None = Field(default=None, ge=1)


class WorkspaceMemberNoteUpdate(BaseModel):
    """红娘说：红娘对会员的公开评价。"""

    note: str = Field(min_length=0, max_length=200)


class WorkspaceMemberNote(BaseModel):
    user_id: int
    note: str
    updated_at: datetime | None = None


class WorkspaceMemberFollowUpCreate(BaseModel):
    method: FollowUpMethod
    content: str = Field(min_length=1, max_length=2000)
    next_follow_at: datetime | None = None


class WorkspaceMemberFollowUp(BaseModel):
    id: int
    user_id: int
    method: FollowUpMethod
    content: str
    next_follow_at: datetime | None
    created_at: datetime


class WorkspaceMemberFollowUpPage(BaseModel):
    items: list[WorkspaceMemberFollowUp]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceMemberContact(BaseModel):
    """服务红娘受审计读取的会员联系方式。

    ``scope`` 说明本次读取依据的权限范围：``ALL`` 表示超级红娘可查看所有会员，
    ``SERVED`` 表示普通红娘仅能查看自己服务范围内的会员。
    """

    user_id: int
    nickname: str | None = None
    real_name: str | None = None
    phone: str | None = None
    wechat: str | None = None
    scope: Literal["ALL", "SERVED"] = "SERVED"


class WorkspaceMatchCandidate(BaseModel):
    user_id: int
    nickname: str
    avatar: str | None
    gender: Literal[1, 2] | None
    birthday: date | None
    residence: str | None
    matchmaker_name: str | None = None


class MemberPartnerPreference(BaseModel):
    """会员择偶要求摘要，空字段由前端展示为“不限”。"""

    age_min: int | None = None
    age_max: int | None = None
    height_min: int | None = None
    height_max: int | None = None
    income_min: float | None = None
    education_min: int | None = None


class WorkspaceMatchCandidatePage(BaseModel):
    items: list[WorkspaceMatchCandidate]
    page: int
    page_size: int
    total: int
    has_more: bool
    preference: MemberPartnerPreference | None = None


class WorkspaceMatchHistoryItem(BaseModel):
    """会员的一条牵线记录（matchmaker_introduction），对方视角。"""

    id: int
    counterpart_user_id: int
    counterpart_nickname: str
    status: IntroductionStatus
    direction: Literal["OUTGOING", "INCOMING"]
    created_at: datetime
    updated_at: datetime


class WorkspaceMatchHistoryPage(BaseModel):
    items: list[WorkspaceMatchHistoryItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceIntroductionPerson(BaseModel):
    user_id: int
    nickname: str
    avatar: str | None
    gender: Literal[1, 2] | None
    is_vip: bool = False


class WorkspaceIntroduction(BaseModel):
    id: int
    status: IntroductionStatus
    failure_reason: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
    from_user: WorkspaceIntroductionPerson
    to_user: WorkspaceIntroductionPerson


class WorkspaceIntroductionPage(BaseModel):
    items: list[WorkspaceIntroduction]
    page: int
    page_size: int
    total: int
    has_more: bool


class WorkspaceMeetingRecordSummary(BaseModel):
    id: int
    status: Literal["SCHEDULED", "REMINDED", "CHECKED_IN", "COMPLETED", "CANCELLED", "NO_SHOW"]
    scheduled_at: datetime
    location: str
    cancel_reason: str | None


class WorkspaceMeetingRequest(BaseModel):
    id: int
    status: Literal["SUBMITTED", "CONTACTED", "ACCEPTED", "DECLINED", "CLOSED"]
    matchmaker_name: str = "待分派"
    note: str
    created_at: datetime
    updated_at: datetime
    applicant: WorkspaceIntroductionPerson
    target: WorkspaceIntroductionPerson
    meeting: WorkspaceMeetingRecordSummary | None


class WorkspaceMeetingRequestPage(BaseModel):
    items: list[WorkspaceMeetingRequest]
    page: int
    page_size: int
    total: int
    has_more: bool


class PartnerTeamUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=128)


class PartnerTeamMember(BaseModel):
    user_id: int
    nickname: str
    joined_at: datetime
    effective_count: int = 0


class PartnerEffectiveMember(BaseModel):
    user_id: int
    nickname: str
    gender: Literal[1, 2] | None
    register_at: datetime
    promoter_name: str


class PartnerLevelInfo(BaseModel):
    """合伙级别按团队业绩与有效会员数双阈值实时计算；level_progress 为到下一级的差距。"""

    level: Literal["初级合伙", "中级合伙", "战略合伙"]
    team_performance: float
    effective_member_count: int
    next_level: str | None = None
    performance_gap: float | None = None
    member_gap: int | None = None


class PartnerCenterProfile(BaseModel):
    nickname: str
    team_name: str | None
    invite_code: str | None
    phone: str | None = None
    wechat_bound: bool = False
    register_at: datetime | None = None


class PromoterRewardItem(BaseModel):
    """注册奖励展示项；合伙人侧与推广红娘侧共用同一展示口径。"""

    user_id: int
    nickname: str
    gender: Literal[1, 2] | None = None
    avatar: str | None = None
    register_at: datetime
    review_status: ReviewStatus
    reward_amount: float = 0


class PartnerCenterSnapshot(BaseModel):
    profile: PartnerCenterProfile
    team_members: list[PartnerTeamMember]
    effective_members: list[PartnerEffectiveMember]
    registration_rewards: list[PromoterRewardItem] = []
    level: PartnerLevelInfo | None = None
    finance_available: Literal[False] = False


class PromoterLeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    wechat: str | None = Field(default=None, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("phone", "wechat", mode="before")
    @classmethod
    def normalize_contact(cls, value: object) -> object:
        if isinstance(value, str):
            return _strip_contact(value)
        return value

    @model_validator(mode="after")
    def require_phone(self) -> "PromoterLeadCreate":
        # 业务口径同录入线索：必须能联系到人，且只有手机号能一键入库成会员。
        if not self.phone:
            raise ValueError("必须登记 11 位手机号")
        return self


class PromoterMember(BaseModel):
    user_id: int
    nickname: str
    gender: Literal[1, 2] | None
    register_at: datetime
    review_status: ReviewStatus


class PromoterCenterProfile(BaseModel):
    nickname: str
    promotion_code: str | None
    phone: str | None = None
    wechat_bound: bool = False
    register_at: datetime | None = None
    team_name: str | None = None
    team_status: Literal["NONE", "PENDING", "ACTIVE"] = "NONE"
    pending_request_id: int | None = None
    level: Literal["初级", "推广大师", "推广大使", "推广天使"] = "初级"
    next_level: str | None = None
    member_gap: int | None = None


class PromoterCenterSnapshot(BaseModel):
    profile: PromoterCenterProfile
    leads: list[WorkspaceLead]
    effective_members: list[PromoterMember]
    incomplete_members: list[PromoterMember]
    rewards: list[PromoterRewardItem] = []
    finance_available: Literal[False] = False


class PartnerJoinRequestCreate(BaseModel):
    """推广红娘凭团队邀请码提交入团申请；合伙人确认后才真正加入团队。"""

    invite_code: str = Field(min_length=4, max_length=64)


class PartnerJoinRequestSummary(BaseModel):
    id: int
    team_id: int
    team_name: str
    promoter_id: int
    promoter_nickname: str | None = None
    promoter_avatar: str | None = None
    status: Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
    created_at: datetime
    reviewed_at: datetime | None = None
    reject_reason: str | None = None


class PartnerJoinRequestReview(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=200)


class PromotionCode(BaseModel):
    code: str
    created_at: datetime


class WorkspaceMemberEntryCreate(BaseModel):
    """服务红娘工作台录入会员；基本信息入库，扩展字段按 user_profile 实际列落库。"""

    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    nickname: str = Field(min_length=1, max_length=64)
    real_name: str | None = Field(default=None, max_length=64)
    gender: Literal[1, 2]
    birthday: date | None = None
    # 与会员端资料编辑页同一套婚况档位（1 未婚 / 2 离异 / 3 丧偶）；库里 4~7 属历史值，只读不再写入。
    is_married: Literal[1, 2, 3] | None = None
    wechat: str | None = Field(default=None, max_length=128)
    height: int | None = Field(default=None, ge=100, le=250)
    weight: int | None = Field(default=None, ge=30, le=150)
    hometown: str | None = Field(default=None, max_length=64)
    residence: str | None = Field(default=None, max_length=64)
    household: str | None = Field(default=None, max_length=64)
    ethnicity: str | None = Field(default=None, max_length=32)
    zodiac: str | None = Field(default=None, max_length=16)
    education: str | None = Field(default=None, max_length=32)
    job: str | None = Field(default=None, max_length=64)
    income: float | None = Field(default=None, ge=0, le=1_000_000)
    house: str | None = Field(default=None, max_length=16)
    car: str | None = Field(default=None, max_length=16)
    smoking: str | None = Field(default=None, max_length=16)
    drinking: str | None = Field(default=None, max_length=16)
    religion: str | None = Field(default=None, max_length=32)
    marriage_plan: str | None = Field(default=None, max_length=64)
    tags: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=2000)
    # 择偶要求（录入时一并写入 user_partner_preference）
    age_min: int | None = Field(default=None, ge=18, le=100)
    age_max: int | None = Field(default=None, ge=18, le=100)
    height_min: int | None = Field(default=None, ge=100, le=250)
    height_max: int | None = Field(default=None, ge=100, le=250)
    education_min: int | None = Field(default=None, ge=1, le=8)
    income_min: float | None = Field(default=None, ge=0, le=1_000_000)
    occupation_requirement: str | None = Field(default=None, max_length=64)
    marriage_accept: Literal["不接受离异", "可接受离异未育", "接受离异带娃", "视情况而定"] | None = None
    housing_requirement: Literal[0, 1, 2] | None = None
    smoking_requirement: Literal[0, 1, 2] | None = None
    wedding_plan: Literal["不限", "计划一年内", "计划两年内", "计划三年内", "时机成熟时结婚", "不婚"] | None = None

    @model_validator(mode="after")
    def validate_pref_ranges(self) -> "WorkspaceMemberEntryCreate":
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("期望年龄下限不能大于上限")
        if self.height_min is not None and self.height_max is not None and self.height_min > self.height_max:
            raise ValueError("期望身高下限不能大于上限")
        return self


class WorkspaceMemberEntryResult(BaseModel):
    member_id: int
    review_status: ReviewStatus
    matchmaker_id: int


class WorkspaceMeetingStatusUpdate(BaseModel):
    """约见申请处理状态流转；待处理=SUBMITTED，已处理=ACCEPTED/DECLINED/CLOSED。"""

    status: Literal["SUBMITTED", "CONTACTED", "ACCEPTED", "DECLINED", "CLOSED"]


class WorkspaceMeetingScheduleCreate(BaseModel):
    """服务红娘为双方接受的约见申请创建约见安排；时间必须晚于当前时刻。"""

    scheduled_at: datetime
    location: str = Field(min_length=1, max_length=128)

    @field_validator("scheduled_at")
    @classmethod
    def require_future_time(cls, value: datetime) -> datetime:
        now = datetime.now(UTC) if value.tzinfo is not None else datetime.now()
        if value <= now:
            raise ValueError("约见时间必须晚于当前时间")
        return value


class WorkspaceMeetingRecordStatusUpdate(BaseModel):
    """约见安排状态流转：进行中=REMINDED/CHECKED_IN，完成=COMPLETED，结束=CANCELLED/NO_SHOW。"""

    status: Literal["REMINDED", "CHECKED_IN", "COMPLETED", "CANCELLED", "NO_SHOW"]
    cancel_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_cancel_reason(self) -> "WorkspaceMeetingRecordStatusUpdate":
        if self.status in {"CANCELLED", "NO_SHOW"} and not (
            self.cancel_reason and str(self.cancel_reason).strip()
        ):
            raise ValueError("取消或爽约必须填写原因")
        if self.status not in {"CANCELLED", "NO_SHOW"} and self.cancel_reason:
            raise ValueError("仅取消或爽约需要填写原因")
        return self


class WorkspaceIntroductionStatusUpdate(BaseModel):
    """牵线状态流转；失败必须给出失败原因，其他状态不允许携带备注。"""

    status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
    failure_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_failure_reason(self) -> "WorkspaceIntroductionStatusUpdate":
        if self.status == "FAILED" and not (self.failure_reason and str(self.failure_reason).strip()):
            raise ValueError("牵线失败必须填写失败原因")
        if self.status != "FAILED" and self.failure_reason:
            raise ValueError("仅牵线失败需要填写失败原因")
        return self


class WorkspaceIntroductionCreate(BaseModel):
    """服务红娘手工添加牵线记录；双方必须是工作范围内会员。"""

    from_user_id: int = Field(ge=1)
    to_user_id: int = Field(ge=1)
    applied_at: date | None = None
    finished_at: date | None = None
    result: Literal["SUCCEEDED", "FAILED"]
    failure_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_pairs(self) -> "WorkspaceIntroductionCreate":
        if self.from_user_id == self.to_user_id:
            raise ValueError("牵线会员与被牵线会员不能是同一人")
        if self.result == "FAILED" and not (self.failure_reason and str(self.failure_reason).strip()):
            raise ValueError("牵线失败必须填写失败原因")
        if self.result == "SUCCEEDED" and self.finished_at is None:
            raise ValueError("牵线成功必须选择牵线完成时间")
        return self


class WorkspaceIntroductionCreated(BaseModel):
    id: int
    status: Literal["PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED"]
