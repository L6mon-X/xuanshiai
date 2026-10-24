"""Mobile service-matchmaker workbench routes protected by normal user JWTs."""

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.auth import (
    CompletionResponse,
    NicknameUpdateRequest,
    NicknameUpdateResponse,
    PreferenceResponse,
    PreferenceUpdateRequest,
    ProfileMediaResponse,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.schemas.matchmaker_workspace import (
    MatchmakerHomepage,
    MatchmakerHomepageUpdate,
    MatchmakerWorkspaceAccess,
    MatchmakerWorkspaceDashboard,
    MatchmakerWorkspaceProfile,
    MatchmakerWorkspaceProfileUpdate,
    PartnerCenterSnapshot,
    PartnerTeamUpdate,
    PromoterCenterSnapshot,
    PromoterLeadCreate,
    PromotionCode,
    WorkspaceAbandonRequest,
    WorkspaceAssignRequest,
    WorkspaceLead,
    WorkspaceLeadConvertRequest,
    WorkspaceLeadConvertResult,
    WorkspaceLeadCreate,
    WorkspaceLeadFollowUp,
    WorkspaceLeadFollowUpCreate,
    WorkspaceLeadFollowUpPage,
    WorkspaceLeadFollower,
    WorkspaceLeadPage,
    WorkspaceLeadUpdate,
    WorkspaceIntroductionCreate,
    WorkspaceIntroductionCreated,
    WorkspaceIntroductionPage,
    WorkspaceMatchCandidatePage,
    WorkspaceMatchHistoryPage,
    WorkspaceMemberContact,
    WorkspaceMemberFollowUp,
    WorkspaceMemberFollowUpCreate,
    WorkspaceMemberFollowUpPage,
    WorkspaceMember,
    WorkspaceMemberMatchmakerUpdate,
    WorkspaceMemberNote,
    WorkspaceMemberNoteUpdate,
    WorkspaceMemberEntryCreate,
    WorkspaceMemberEntryResult,
    WorkspaceMemberPage,
    WorkspaceMemberReviewUpdate,
    WorkspaceMeetingRequestPage,
    WorkspaceMeetingRecordSummary,
    WorkspaceIntroductionStatusUpdate,
    WorkspaceMeetingScheduleCreate,
    WorkspaceMeetingRecordStatusUpdate,
    WorkspaceMeetingStatusUpdate,
    PartnerJoinRequestCreate,
    PartnerJoinRequestReview,
    PartnerJoinRequestSummary,
)
from app.services.matchmaker_workspace import (
    abandon_workspace_lead,
    add_workspace_lead_follow_up,
    assign_workspace_lead,
    assign_workspace_member_matchmaker,
    cancel_partner_join_request,
    convert_workspace_lead,
    create_member_follow_up,
    create_partner_invite,
    create_promoter_code,
    create_promoter_lead,
    create_workspace_lead,
    create_workspace_member,
    get_member_contact,
    get_partner_center,
    get_promoter_center,
    get_workspace_member_note,
    get_workspace_profile,
    get_workspace_homepage,
    list_match_candidates,
    list_match_history,
    list_member_matchmakers,
    list_partner_join_requests,
    list_workspace_colleagues,
    list_workspace_introductions,
    list_workspace_lead_follow_ups,
    list_workspace_meeting_requests,
    delete_workspace_meeting_request,
    review_partner_join_request,
    schedule_workspace_meeting,
    submit_partner_join_request,
    create_team_qr_code,
    update_workspace_meeting_record_status,
    create_workspace_introduction,
    update_workspace_introduction_status,
    update_workspace_meeting_status,
    list_member_follow_ups,
    list_workspace_leads,
    list_workspace_members,
    require_workspace,
    restore_workspace_lead,
    review_workspace_member,
    update_partner_team,
    update_workspace_lead,
    update_workspace_member_note,
    update_workspace_homepage,
    update_workspace_profile,
    upload_lead_photo,
    workspace_access,
    workspace_dashboard,
)
from app.services.matchmaker_member_profile import (
    delete_member_photo,
    get_member_completion,
    get_member_preferences,
    get_member_profile,
    update_member_nickname,
    update_member_preferences,
    update_member_profile,
    upload_member_avatar,
    upload_member_background,
    upload_member_photo,
)


router = APIRouter(prefix="/matchmaker")


@router.get("/management-center/access", response_model=MatchmakerWorkspaceAccess, summary="查询服务红娘工作台准入")
async def management_center_access(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchmakerWorkspaceAccess:
    return await workspace_access(db, current)


@router.get("/management-center/dashboard", response_model=MatchmakerWorkspaceDashboard, summary="查询服务红娘工作台概览")
async def management_center_dashboard(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchmakerWorkspaceDashboard:
    return await workspace_dashboard(db, await require_workspace(db, current))


@router.get("/workbench/profile", response_model=MatchmakerWorkspaceProfile, summary="查询红娘展示资料")
async def workbench_profile(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchmakerWorkspaceProfile:
    return await get_workspace_profile(db, await require_workspace(db, current))


@router.patch("/workbench/profile", response_model=MatchmakerWorkspaceProfile, summary="修改红娘展示昵称")
async def update_workbench_profile(
    body: MatchmakerWorkspaceProfileUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchmakerWorkspaceProfile:
    return await update_workspace_profile(db, await require_workspace(db, current), body)


@router.get("/workbench/homepage", response_model=MatchmakerHomepage, summary="查询红娘可编辑的主页资料")
async def workbench_homepage(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchmakerHomepage:
    return await get_workspace_homepage(db, await require_workspace(db, current))


@router.patch("/workbench/homepage", response_model=MatchmakerHomepage, summary="保存红娘主页资料")
async def update_workbench_homepage(
    body: MatchmakerHomepageUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchmakerHomepage:
    return await update_workspace_homepage(db, await require_workspace(db, current), body)


@router.get("/workbench/leads", response_model=WorkspaceLeadPage, summary="查询工作范围内客源线索")
async def workbench_leads(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(NEW|CONTACTED|INTENDED|CONVERTED|LOST|CLOSED)$"),
    search: str | None = Query(None, max_length=64),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLeadPage:
    return await list_workspace_leads(db, await require_workspace(db, current), page, page_size, status, search)


@router.post("/workbench/leads", response_model=WorkspaceLead, status_code=201, summary="录入工作范围客源线索")
async def create_workbench_lead(
    body: WorkspaceLeadCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await create_workspace_lead(db, await require_workspace(db, current), body)


@router.post("/workbench/leads/photo", status_code=201, summary="上传客源线索照片")
async def upload_workbench_lead_photo(
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传客源照片，返回可直接存入 customer_lead.photo 的 URL。"""
    return await upload_lead_photo(db, await require_workspace(db, current), file)


@router.patch("/workbench/leads/{lead_id}", response_model=WorkspaceLead, summary="修改工作范围客源线索")
async def patch_workbench_lead(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceLeadUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await update_workspace_lead(db, await require_workspace(db, current), lead_id, body)


@router.post("/workbench/leads/{lead_id}/follow-ups", response_model=WorkspaceLeadFollowUp, status_code=201, summary="新增客源跟进")
async def create_workbench_lead_follow_up(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceLeadFollowUpCreate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLeadFollowUp:
    return await add_workspace_lead_follow_up(db, await require_workspace(db, current), lead_id, body)


@router.post("/workbench/leads/{lead_id}/abandon", response_model=WorkspaceLead, summary="弃海工作范围客源")
async def abandon_workbench_lead(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceAbandonRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await abandon_workspace_lead(db, await require_workspace(db, current), lead_id, body)


@router.get("/workbench/leads/{lead_id}/follow-ups", response_model=WorkspaceLeadFollowUpPage, summary="查询客源跟进记录")
async def workbench_lead_follow_ups(
    lead_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLeadFollowUpPage:
    return await list_workspace_lead_follow_ups(db, await require_workspace(db, current), lead_id, page, page_size)


@router.get("/workbench/leads/followers", response_model=list[WorkspaceLeadFollower], summary="查询可分派跟进的同组织红娘")
async def workbench_lead_followers(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceLeadFollower]:
    return await list_workspace_colleagues(db, await require_workspace(db, current))


@router.post("/workbench/leads/{lead_id}/assign", response_model=WorkspaceLead, summary="分派客源跟进红娘")
async def assign_workbench_lead(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceAssignRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await assign_workspace_lead(db, await require_workspace(db, current), lead_id, body)


@router.post("/workbench/leads/{lead_id}/convert", response_model=WorkspaceLeadConvertResult, summary="一键入库客源为正式用户")
async def convert_workbench_lead(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceLeadConvertRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLeadConvertResult:
    return await convert_workspace_lead(db, await require_workspace(db, current), lead_id, body)


@router.post("/workbench/leads/{lead_id}/restore", response_model=WorkspaceLead, summary="恢复弃海客源")
async def restore_workbench_lead(
    lead_id: int = Path(..., ge=1),
    body: WorkspaceAbandonRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await restore_workspace_lead(db, await require_workspace(db, current), lead_id, body)


@router.get("/workbench/members", response_model=WorkspaceMemberPage, summary="查询工作范围会员和公开资料审核状态")
async def workbench_members(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    review_status: str | None = Query(None, pattern="^(PENDING|PASSED|REJECTED)$"),
    search: str | None = Query(None, max_length=64),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberPage:
    return await list_workspace_members(db, await require_workspace(db, current), page, page_size, review_status, search)


@router.get("/workbench/introductions", response_model=WorkspaceIntroductionPage, summary="查询工作范围内牵线记录")
async def workbench_introductions(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(PENDING|IN_PROGRESS|SUCCEEDED|FAILED)$"),
    search: str | None = Query(None, max_length=64),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceIntroductionPage:
    return await list_workspace_introductions(db, await require_workspace(db, current), page, page_size, status, search)


@router.get("/workbench/meeting-requests", response_model=WorkspaceMeetingRequestPage, summary="查询工作范围内约见申请")
async def workbench_meeting_requests(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=64),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMeetingRequestPage:
    return await list_workspace_meeting_requests(db, await require_workspace(db, current), page, page_size, search)


@router.patch("/workbench/members/{member_id}/public-profile-review", response_model=WorkspaceMember, summary="审核会员公开资料")
async def review_workbench_member(
    member_id: int = Path(..., ge=1),
    body: WorkspaceMemberReviewUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    return await review_workspace_member(db, await require_workspace(db, current), member_id, body)


@router.get(
    "/workbench/members/{member_id}/profile",
    response_model=ProfileResponse,
    summary="服务红娘查看会员完整资料",
)
async def workbench_member_profile(
    member_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回与「我的资料」同构的会员资料，供红娘代编页直接回填。"""
    await require_workspace(db, current)
    return await get_member_profile(db, member_id)


@router.patch(
    "/workbench/members/{member_id}/profile",
    response_model=ProfileResponse,
    summary="服务红娘修改会员资料",
)
async def update_workbench_member_profile(
    member_id: int = Path(..., ge=1),
    body: ProfileUpdateRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """代会员更新资料并重算完整度，允许修正性别。"""
    await require_workspace(db, current)
    return await update_member_profile(db, member_id, body)


@router.get(
    "/workbench/members/{member_id}/preferences",
    response_model=PreferenceResponse,
    summary="服务红娘查看会员择偶要求",
)
async def workbench_member_preferences(
    member_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace(db, current)
    return await get_member_preferences(db, member_id)


@router.put(
    "/workbench/members/{member_id}/preferences",
    response_model=PreferenceResponse,
    summary="服务红娘修改会员择偶要求",
)
async def update_workbench_member_preferences(
    member_id: int = Path(..., ge=1),
    body: PreferenceUpdateRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace(db, current)
    return await update_member_preferences(db, member_id, body)


@router.get(
    "/workbench/members/{member_id}/completion",
    response_model=CompletionResponse,
    summary="服务红娘查询会员资料完整度",
)
async def workbench_member_completion(
    member_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompletionResponse:
    await require_workspace(db, current)
    return await get_member_completion(db, member_id)


@router.patch(
    "/workbench/members/{member_id}/nickname",
    response_model=NicknameUpdateResponse,
    summary="服务红娘修改会员昵称",
)
async def update_workbench_member_nickname(
    member_id: int = Path(..., ge=1),
    body: NicknameUpdateRequest = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NicknameUpdateResponse:
    await require_workspace(db, current)
    return await update_member_nickname(db, member_id, body.nickname)


@router.post(
    "/workbench/members/{member_id}/avatar",
    response_model=ProfileMediaResponse,
    status_code=201,
    summary="服务红娘代传会员头像",
)
async def upload_workbench_member_avatar(
    member_id: int = Path(..., ge=1),
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """代传头像直接审核通过，保存后立即在会员主页展示。"""
    await require_workspace(db, current)
    return await upload_member_avatar(db, member_id, file)


@router.post(
    "/workbench/members/{member_id}/background",
    response_model=ProfileMediaResponse,
    status_code=201,
    summary="服务红娘代传会员主页背景墙",
)
async def upload_workbench_member_background(
    member_id: int = Path(..., ge=1),
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace(db, current)
    return await upload_member_background(db, member_id, file)


@router.post(
    "/workbench/members/{member_id}/photos",
    response_model=ProfileMediaResponse,
    status_code=201,
    summary="服务红娘代传会员相册图片",
)
async def upload_workbench_member_photo(
    member_id: int = Path(..., ge=1),
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace(db, current)
    return await upload_member_photo(db, member_id, file)


@router.delete(
    "/workbench/members/{member_id}/photos/{media_id}",
    status_code=204,
    summary="服务红娘删除会员相册图片",
)
async def remove_workbench_member_photo(
    member_id: int = Path(..., ge=1),
    media_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await require_workspace(db, current)
    await delete_member_photo(db, member_id, media_id)


@router.get("/workbench/members/{member_id}/follow-ups", response_model=WorkspaceMemberFollowUpPage, summary="查询会员服务跟进")
async def workbench_member_follow_ups(
    member_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberFollowUpPage:
    return await list_member_follow_ups(db, await require_workspace(db, current), member_id, page, page_size)


@router.post("/workbench/members/{member_id}/follow-ups", response_model=WorkspaceMemberFollowUp, status_code=201, summary="新增会员服务跟进")
async def create_workbench_member_follow_up(
    member_id: int = Path(..., ge=1),
    body: WorkspaceMemberFollowUpCreate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberFollowUp:
    return await create_member_follow_up(db, await require_workspace(db, current), member_id, body)


@router.get("/workbench/members/{member_id}/contact", response_model=WorkspaceMemberContact, summary="受审计读取会员联系方式")
async def workbench_member_contact(
    member_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberContact:
    return await get_member_contact(db, await require_workspace(db, current), member_id)


@router.get("/workbench/members/{member_id}/match-candidates", response_model=WorkspaceMatchCandidatePage, summary="查询只读牵线候选人")
async def workbench_match_candidates(
    member_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMatchCandidatePage:
    return await list_match_candidates(db, await require_workspace(db, current), member_id, page, page_size)


@router.get("/workbench/members/{member_id}/match-history", response_model=WorkspaceMatchHistoryPage, summary="查询只读牵线历史")
async def workbench_match_history(
    member_id: int = Path(..., ge=1),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMatchHistoryPage:
    return await list_match_history(db, await require_workspace(db, current), member_id, page, page_size)


@router.get("/workbench/matchmakers", response_model=list[WorkspaceLeadFollower], summary="查询可改派的服务红娘")
async def workbench_matchmakers(
    member_id: int = Query(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceLeadFollower]:
    return await list_member_matchmakers(db, await require_workspace(db, current), member_id)


@router.patch("/workbench/members/{member_id}/assignment", response_model=WorkspaceMember, summary="修改会员跟进服务红娘")
async def assign_workbench_member(
    member_id: int = Path(..., ge=1),
    body: WorkspaceMemberMatchmakerUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    return await assign_workspace_member_matchmaker(db, await require_workspace(db, current), member_id, body)


@router.get("/workbench/members/{member_id}/note", response_model=WorkspaceMemberNote, summary="查询红娘说公开评价")
async def workbench_member_note(
    member_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberNote:
    return await get_workspace_member_note(db, await require_workspace(db, current), member_id)


@router.patch("/workbench/members/{member_id}/note", response_model=WorkspaceMemberNote, summary="保存红娘说公开评价")
async def update_workbench_member_note(
    member_id: int = Path(..., ge=1),
    body: WorkspaceMemberNoteUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberNote:
    return await update_workspace_member_note(db, await require_workspace(db, current), member_id, body)


@router.get("/partner-center", response_model=PartnerCenterSnapshot, summary="查询合伙人中心")
async def partner_center(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PartnerCenterSnapshot:
    return await get_partner_center(db, current)


@router.put("/partner-center/team", response_model=PartnerCenterSnapshot, summary="创建或修改自己的合伙团队")
async def put_partner_team(
    body: PartnerTeamUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerCenterSnapshot:
    return await update_partner_team(db, current, body)


@router.post("/partner-center/invites", response_model=PromotionCode, status_code=201, summary="生成自己的团队邀请代码")
async def create_partner_team_invite(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PromotionCode:
    return await create_partner_invite(db, current)


@router.get("/promoter-center", response_model=PromoterCenterSnapshot, summary="查询推广红娘中心")
async def promoter_center(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PromoterCenterSnapshot:
    return await get_promoter_center(db, current)


@router.post("/promoter-center/leads", response_model=WorkspaceLead, status_code=201, summary="推广红娘录入自己的客源")
async def create_promoter_center_lead(
    body: PromoterLeadCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceLead:
    return await create_promoter_lead(db, current, body)


@router.post("/promoter-center/promotion-codes", response_model=PromotionCode, status_code=201, summary="生成自己的推广代码")
async def create_promoter_center_code(
    current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PromotionCode:
    return await create_promoter_code(db, current)


@router.post(
    "/promoter-center/team-requests",
    response_model=PartnerJoinRequestSummary,
    status_code=201,
    summary="凭团队邀请码提交入团申请",
)
async def submit_promoter_team_request(
    body: PartnerJoinRequestCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerJoinRequestSummary:
    return await submit_partner_join_request(db, current, body)


@router.delete(
    "/promoter-center/team-requests/{request_id}",
    status_code=204,
    summary="撤回自己的入团申请",
)
async def cancel_promoter_team_request(
    request_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await cancel_partner_join_request(db, current, request_id)


@router.get(
    "/partner-center/join-requests",
    response_model=list[PartnerJoinRequestSummary],
    summary="查询团队的入团申请",
)
async def list_partner_center_join_requests(
    status: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerJoinRequestSummary]:
    return await list_partner_join_requests(db, current, status)


@router.patch(
    "/partner-center/join-requests/{request_id}",
    response_model=PartnerJoinRequestSummary,
    summary="审批入团申请（通过/拒绝）",
)
async def review_partner_center_join_request(
    request_id: int = Path(..., ge=1),
    body: PartnerJoinRequestReview = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerJoinRequestSummary:
    return await review_partner_join_request(db, current, request_id, body)


@router.post(
    "/partner-center/qrcode",
    summary="生成团队邀请小程序码（base64 图片）",
)
async def create_partner_center_qrcode(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await create_team_qr_code(db, current)


@router.post(
    "/workbench/members",
    response_model=WorkspaceMemberEntryResult,
    status_code=201,
    summary="服务红娘录入会员",
)
async def create_workbench_member(
    body: WorkspaceMemberEntryCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMemberEntryResult:
    return await create_workspace_member(db, current, body)


@router.patch(
    "/workbench/meeting-requests/{request_id}/status",
    status_code=204,
    summary="更新约见申请处理状态",
)
async def update_workbench_meeting_status(
    request_id: int = Path(..., ge=1),
    body: WorkspaceMeetingStatusUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await update_workspace_meeting_status(db, await require_workspace(db, current), request_id, body.status)


@router.delete(
    "/workbench/meeting-requests/{request_id}",
    status_code=204,
    summary="删除约见申请记录",
)
async def delete_workbench_meeting_request(
    request_id: int = Path(..., ge=1),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_workspace_meeting_request(db, await require_workspace(db, current), request_id)


@router.post(
    "/workbench/meeting-requests/{request_id}/schedule",
    response_model=WorkspaceMeetingRecordSummary,
    status_code=201,
    summary="为双方接受的约见申请安排约见",
)
async def schedule_workbench_meeting(
    request_id: int = Path(..., ge=1),
    body: WorkspaceMeetingScheduleCreate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMeetingRecordSummary:
    return await schedule_workspace_meeting(db, await require_workspace(db, current), request_id, body)


@router.patch(
    "/workbench/meetings/{meeting_id}/status",
    status_code=204,
    summary="更新约见安排状态（提醒/签到/完成/取消/爽约）",
)
async def update_workbench_meeting_record_status(
    meeting_id: int = Path(..., ge=1),
    body: WorkspaceMeetingRecordStatusUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await update_workspace_meeting_record_status(db, await require_workspace(db, current), meeting_id, body)


@router.patch(
    "/workbench/introductions/{introduction_id}/status",
    status_code=204,
    summary="更新牵线状态",
)
async def update_workbench_introduction_status(
    introduction_id: int = Path(..., ge=1),
    body: WorkspaceIntroductionStatusUpdate = ...,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await update_workspace_introduction_status(db, await require_workspace(db, current), introduction_id, body.status, body.failure_reason)


@router.post(
    "/workbench/introductions",
    response_model=WorkspaceIntroductionCreated,
    status_code=201,
    summary="添加牵线记录",
)
async def create_workbench_introduction(
    body: WorkspaceIntroductionCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceIntroductionCreated:
    return await create_workspace_introduction(db, await require_workspace(db, current), body)
