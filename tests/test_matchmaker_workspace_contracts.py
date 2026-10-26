from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.main import app
from app.schemas.customer_lead_admin import CustomerLeadCreate, CustomerLeadUpdate
from app.schemas.matchmaker_workspace import (
    MatchmakerWorkspaceProfileUpdate,
    PromoterLeadCreate,
    WorkspaceLeadCreate,
    WorkspaceLeadUpdate,
    WorkspaceMemberReviewUpdate,
)
from app.services.customer_lead_contact import normalize_contact
from app.services.matchmaker_workspace import WorkspaceActor, require_review_authority


client = TestClient(app)


def test_workspace_routes_are_registered_and_require_normal_user_authentication() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/matchmaker/management-center/access",
        "/api/v1/matchmaker/management-center/dashboard",
        "/api/v1/matchmaker/workbench/members",
        "/api/v1/matchmaker/workbench/introductions",
        "/api/v1/matchmaker/workbench/meeting-requests",
        "/api/v1/matchmaker/workbench/members/{member_id}/contact",
        "/api/v1/matchmaker/partner-center",
        "/api/v1/matchmaker/promoter-center",
        "/api/v1/matchmaker/promoter-center/leads",
    }
    assert expected <= set(paths)
    assert client.get("/api/v1/matchmaker/management-center/access").status_code == 401
    assert paths["/api/v1/matchmaker/workbench/members"]["get"].get("security")


def test_public_profile_review_is_limited_to_headquarters_matchmakers() -> None:
    """审核闸门：只有总店（SUPER）红娘能判定通过/驳回，普通红娘 403。"""
    headquarters = WorkspaceActor(user_id=2, display_name="总店红娘", level="SUPER", organization_id=None)
    ordinary = WorkspaceActor(user_id=21, display_name="普通红娘", level="NORMAL", organization_id=None)
    assert require_review_authority(headquarters) is headquarters
    with pytest.raises(HTTPException) as excinfo:
        require_review_authority(ordinary)
    assert excinfo.value.status_code == 403
    assert "总店" in excinfo.value.detail


def test_workspace_schemas_enforce_non_payment_and_review_boundaries() -> None:
    assert MatchmakerWorkspaceProfileUpdate(display_name="林老师").display_name == "林老师"
    assert WorkspaceLeadCreate(name="王女士", phone="13800000000", source="线下活动").intention_level == 1
    assert PromoterLeadCreate(name="李先生", phone="13800000000", wechat="wxid_123", source="朋友介绍").name == "李先生"
    assert WorkspaceMemberReviewUpdate(status="PASSED").reason is None
    with pytest.raises(ValidationError):
        WorkspaceLeadCreate(name="王女士", source="线下活动")
    with pytest.raises(ValidationError):
        PromoterLeadCreate(name="李先生", wechat="wxid_123", source="朋友介绍")
    with pytest.raises(ValidationError):
        WorkspaceMemberReviewUpdate(status="REJECTED")


def test_lead_contact_schemas_normalize_and_require_a_valid_phone() -> None:
    """录入线索口径：手机号必填且必须是 11 位有效号码；首尾空白归一化，空串视为未提供。"""
    assert WorkspaceLeadCreate(name="王女士", phone=" 13800000000 ", wechat="", source="线下活动").phone == "13800000000"
    assert WorkspaceLeadUpdate(phone=" 13800000000 ").phone == "13800000000"
    assert PromoterLeadCreate(name="李先生", phone="13800000000", wechat=" wxid_123 ", source="朋友介绍").wechat == "wxid_123"
    assert CustomerLeadCreate(name="王女士", phone=" 13800000000 ", source="线下活动").phone == "13800000000"
    assert CustomerLeadUpdate(name="王女士", wechat="  ").wechat is None
    # 后台表单预填的脱敏手机号（139****0101）视同「未修改」，整键丢弃而不是 422。
    assert CustomerLeadUpdate(name="王女士", phone="139****0101").model_dump(exclude_unset=True) == {"name": "王女士"}
    with pytest.raises(ValidationError):
        WorkspaceLeadCreate(name="王女士", phone="", wechat=" wx_a ", source="线下活动")
    with pytest.raises(ValidationError):
        WorkspaceLeadCreate(name="王女士", phone=" 138-0000-0000 ", source="线下活动")
    with pytest.raises(ValidationError):
        WorkspaceLeadCreate(name="王女士", phone="   ", wechat=None, source="线下活动")
    with pytest.raises(ValidationError):
        # 手机号只能改成有效号码，不能清空。
        WorkspaceLeadUpdate(phone="")
    with pytest.raises(ValidationError):
        CustomerLeadUpdate(phone=None)
    with pytest.raises(ValidationError):
        # 仅提交空白联系方式等价于没有任何修改项。
        CustomerLeadUpdate(wechat="  ")


def test_lead_update_accepts_the_source_channel_from_the_create_form() -> None:
    """后台「编辑客源」与录入同一套表单，来源必须可改；空白来源仍是无效输入。"""
    assert CustomerLeadUpdate(source="本地群").model_dump(exclude_unset=True) == {"source": "本地群"}
    with pytest.raises(ValidationError):
        CustomerLeadUpdate(source="")


def test_normalize_contact_treats_blank_as_missing() -> None:
    assert normalize_contact("  13800000000  ") == "13800000000"
    assert normalize_contact("   ") is None
    assert normalize_contact(None) is None
    assert normalize_contact(13800000000) == "13800000000"
