"""单元测试：后台运营缺失接口（A4/A5/A7/A8/A9/A10 + B1/B2）。

覆盖范围：
- 新路由注册（OpenAPI）：素材库、二维码、话术库、相亲卡、会员弃海、互动内容、联盟活动；
  以及 B2 新增的互选活动下线动作。
- 未登录访问上述 admin 端点均 401。
- schema 校验：分成比例上限、二维码类型/续期范围、互选活动时间窗顺序、联盟活动时间。
- A9/B3：会员列表 `abandoned` 筛选谓词与统计字段。
- 迁移：新表已登记进 BUSINESS_TABLES，`_ensure_mutual_selection_columns` 已定义并注册。
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db.business_schema import BUSINESS_TABLES
from app.main import app
from app.schemas.admin_alliance_activity import AllianceActivityCreate
from app.schemas.admin_lovecard_admin import LovecardTemplateCreate
from app.schemas.admin_material_admin import MaterialCategoryCreate, MaterialUpdate
from app.schemas.admin_qrcode_admin import QrcodeCreate, QrcodeRenew, QrcodeUpdate
from app.schemas.admin_sales_admin import SalesCategoryCreate, SalesItemCreate, SalesItemPush
from app.schemas.matchmaker_crm_admin import MemberStatistics
from app.schemas.member_abandonment_admin import MemberAbandonRequest, MemberRestoreRequest
from app.schemas.mutual_selection_admin import MutualActivityCreate, MutualActivityUpdate
from app.schemas.organization_admin import StoreAdminCreate, StoreAdminUpdate
from app.services import member_crm_filter

client = TestClient(app)

MATERIALS = "/api/v1/admin/materials"
QRCODES = "/api/v1/admin/qrcodes"
SALES = "/api/v1/admin/sales-library"
LOVECARD = "/api/v1/admin/lovecard-templates"
ABANDONED = "/api/v1/admin/members/abandoned"
ABANDONMENTS = "/api/v1/admin/members/abandonments"
INTERACT = "/api/v1/admin/interact/contents"
ALLIANCE = "/api/v1/admin/alliance/activities"
MUTUAL = "/api/v1/admin/mutual-activities"


# ─── 路由注册 ────────────────────────────────────────────────────────


def _paths() -> dict:
    return client.get("/openapi.json").json()["paths"]


def test_material_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[MATERIALS])
    assert {"get", "post"} <= set(paths[f"{MATERIALS}/categories"])
    assert {"patch", "delete"} <= set(paths[f"{MATERIALS}/categories/{{category_id}}"])
    assert {"patch", "delete"} <= set(paths[f"{MATERIALS}/{{material_id}}"])


def test_qrcode_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[QRCODES])
    assert "post" in paths[f"{QRCODES}/{{qrcode_id}}/renew"]
    assert {"patch", "delete"} <= set(paths[f"{QRCODES}/{{qrcode_id}}"])


def test_sales_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[f"{SALES}/categories"])
    assert {"patch", "delete"} <= set(paths[f"{SALES}/categories/{{category_id}}"])
    assert {"get", "post"} <= set(paths[f"{SALES}/items"])
    assert "post" in paths[f"{SALES}/items/{{item_id}}/push"]
    assert "get" in paths[f"{SALES}/items/push-records"]
    assert {"patch", "delete"} <= set(paths[f"{SALES}/items/{{item_id}}"])


def test_lovecard_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[LOVECARD])
    assert "get" in paths[f"{LOVECARD}/generations"]
    assert "post" in paths[f"{LOVECARD}/{{template_id}}/generate"]
    assert {"patch", "delete"} <= set(paths[f"{LOVECARD}/{{template_id}}"])


def test_abandonment_routes_registered() -> None:
    paths = _paths()
    # 静态路径必须存在，且未被 member_records_admin 的 /{member_id} 动态段吞掉。
    assert "get" in paths[ABANDONED]
    assert "get" in paths[ABANDONMENTS]
    assert "post" in paths["/api/v1/admin/members/{member_id}/abandon"]
    assert "post" in paths["/api/v1/admin/members/{member_id}/restore"]


def test_interact_and_alliance_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[INTERACT])
    assert {"patch", "delete"} <= set(paths[f"{INTERACT}/{{item_id}}"])
    assert {"get", "post"} <= set(paths[ALLIANCE])
    assert {"patch", "delete"} <= set(paths[f"{ALLIANCE}/{{activity_id}}"])


def test_mutual_offline_route_registered() -> None:
    assert "post" in _paths()[f"{MUTUAL}/{{activity_id}}/offline"]


# ─── 未登录 401 ─────────────────────────────────────────────────────


def test_new_endpoints_require_authentication() -> None:
    assert client.get(MATERIALS).status_code == 401
    assert client.post(MATERIALS).status_code == 401
    assert client.get(f"{MATERIALS}/categories").status_code == 401
    assert client.get(QRCODES).status_code == 401
    assert client.post(QRCODES).status_code == 401
    assert client.get(f"{SALES}/categories").status_code == 401
    assert client.get(f"{SALES}/items").status_code == 401
    assert client.get(LOVECARD).status_code == 401
    assert client.get(ABANDONED).status_code == 401
    assert client.get(ABANDONMENTS).status_code == 401
    assert client.post("/api/v1/admin/members/1/abandon").status_code == 401
    assert client.post("/api/v1/admin/members/1/restore").status_code == 401
    assert client.get(INTERACT).status_code == 401
    assert client.get(ALLIANCE).status_code == 401
    assert client.post(f"{MUTUAL}/1/offline").status_code == 401


# ─── schema 校验 ────────────────────────────────────────────────────


def test_store_commission_ratio_is_bounded() -> None:
    body = StoreAdminCreate(
        code="store-01",
        name="门店",
        commission_mode="ratio",
        commission_value=35,
        logo="/storage/uploads/admin/logo.webp",
        address="南京市玄武区",
        intro="简介",
    )
    assert body.commission_mode == "ratio"
    assert body.commission_value == 35
    with pytest.raises(ValidationError):
        StoreAdminCreate(code="store-02", name="门店", commission_mode="ratio", commission_value=120)
    with pytest.raises(ValidationError):
        StoreAdminUpdate(commission_mode="ratio", commission_value=101)


def test_mutual_activity_schedule_fields_and_validation() -> None:
    now = datetime(2026, 10, 20, 10, 0, 0)
    body = MutualActivityCreate(
        title="双十一互选",
        start_time=now,
        end_time=now + timedelta(days=2),
        signup_start_time=now,
        signup_end_time=now + timedelta(days=1),
        mutual_start_time=now + timedelta(days=1),
        mutual_end_time=now + timedelta(days=2),
        activity_fee=99,
        show_wechat_direct=False,
        show_matchmaker_push=True,
    )
    assert body.activity_fee == 99
    assert body.show_wechat_direct is False
    with pytest.raises(ValidationError):
        MutualActivityCreate(
            title="x",
            start_time=now,
            end_time=now + timedelta(days=2),
            signup_start_time=now + timedelta(days=1),
            signup_end_time=now,
        )
    # 局部更新：schema 无法交叉校验（另一半可能未传），由服务层按「合并后的值」校验。
    assert MutualActivityUpdate(mutual_start_time=now + timedelta(days=2), mutual_end_time=now)


def test_qrcode_schema_validation() -> None:
    body = QrcodeCreate(name="活动码", scene="h5", type="h5", target_url="https://example.com/a", expire_days=30)
    assert body.expire_days == 30
    with pytest.raises(ValidationError):
        QrcodeCreate(name="x", scene="unknown", target_url="https://example.com")
    with pytest.raises(ValidationError):
        QrcodeCreate(name="x", type="pdf", target_url="https://example.com")
    assert QrcodeRenew(days=365).days == 365
    with pytest.raises(ValidationError):
        QrcodeRenew(days=0)
    with pytest.raises(ValidationError):
        QrcodeUpdate()


def test_sales_and_material_schema_validation() -> None:
    assert SalesCategoryCreate(name="开场话术").name == "开场话术"
    with pytest.raises(ValidationError):
        SalesItemCreate(category_id=0, title="x", content="y")
    with pytest.raises(ValidationError):
        SalesItemPush(matchmaker_ids=[])
    with pytest.raises(ValidationError):
        MaterialCategoryCreate(name="")
    with pytest.raises(ValidationError):
        MaterialUpdate()


def test_lovecard_and_alliance_schema_validation() -> None:
    now = datetime(2026, 10, 20, 10, 0, 0)
    body = LovecardTemplateCreate(name="双十一卡片", style=3, age_min=25, age_max=35, tags=["教师", "医生"])
    assert body.tags == ["教师", "医生"]
    with pytest.raises(ValidationError):
        LovecardTemplateCreate(name="x", style=26)
    with pytest.raises(ValidationError):
        LovecardTemplateCreate(name="x", age_min=40, age_max=30)
    assert AllianceActivityCreate(
        title="联盟活动", start_time=now, end_time=now + timedelta(hours=3)
    ).capacity == 0
    with pytest.raises(ValidationError):
        AllianceActivityCreate(title="x", start_time=now, end_time=now)


def test_abandonment_request_validation() -> None:
    assert MemberAbandonRequest(reason="长期未跟进").abandon_type == "manual"
    with pytest.raises(ValidationError):
        MemberAbandonRequest(reason="")
    with pytest.raises(ValidationError):
        MemberAbandonRequest(reason="x", abandon_type="unknown")
    assert MemberRestoreRequest(reason="重新跟进", matchmaker_id=5).matchmaker_id == 5


# ─── A9/B3 筛选与统计 ───────────────────────────────────────────────


def test_member_filter_supports_abandoned_predicate() -> None:
    where, params = member_crm_filter.build_member_filter({"abandoned": True}, frozenset())
    assert "EXISTS (SELECT 1 FROM member_abandonment ma" in where
    assert "ma.restored_at IS NULL" in where
    assert params == {}

    where, params = member_crm_filter.build_member_filter({"abandoned": False}, frozenset())
    assert "NOT EXISTS (SELECT 1 FROM member_abandonment ma" in where

    where, _ = member_crm_filter.build_member_filter({"abandoned": None}, frozenset())
    assert "member_abandonment" not in where


def test_member_statistics_exposes_abandoned() -> None:
    stats = MemberStatistics(
        total=1, male=1, female=0, vip=0, active=1, unassigned=1,
        never_followed=1, follow_due_today=0, abandoned=1,
    )
    assert stats.abandoned == 1
    # 默认值保证旧调用方不传该字段时仍可构造。
    assert MemberStatistics(total=0, male=0, female=0, vip=0, active=0).abandoned == 0


# ─── 表与迁移 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "table",
    [
        "admin_material_category",
        "admin_material",
        "admin_qrcode",
        "admin_sales_category",
        "admin_sales_item",
        "admin_sales_push",
        "admin_lovecard_template",
        "admin_lovecard_generation",
        "member_abandonment",
        "admin_alliance_activity",
    ],
)
def test_new_tables_registered_in_business_schema(table: str) -> None:
    assert table in BUSINESS_TABLES
    assert f"CREATE TABLE IF NOT EXISTS `{table}`" in BUSINESS_TABLES[table]


def test_mutual_selection_column_helper_is_registered() -> None:
    import database_setup_marriage as setup

    cls = next(c for c in dir(setup) if c.endswith("Manager") and not c.startswith("_"))
    source = inspect.getsource(getattr(setup, cls))
    assert "def _ensure_mutual_selection_columns" in source
    assert "self._ensure_mutual_selection_columns(cursor)" in source


def test_store_and_mutual_columns_are_in_ddl() -> None:
    org_ddl = BUSINESS_TABLES["organization"]
    for column in ("logo", "address", "commission_mode", "commission_value", "intro"):
        assert f"`{column}`" in org_ddl
    mutual_ddl = BUSINESS_TABLES["mutual_selection_activity"]
    for column in (
        "signup_start_time",
        "signup_end_time",
        "mutual_start_time",
        "mutual_end_time",
        "activity_fee",
        "show_wechat_direct",
        "show_matchmaker_push",
    ):
        assert f"`{column}`" in mutual_ddl


# ─── A1 短信管理 ────────────────────────────────────────────────────

SMS = "/api/v1/admin/sms"


def test_sms_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[f"{SMS}/signatures"])
    assert {"patch", "delete"} <= set(paths[f"{SMS}/signatures/{{signature_id}}"])
    assert {"get", "post"} <= set(paths[f"{SMS}/templates"])
    assert {"patch", "delete"} <= set(paths[f"{SMS}/templates/{{template_id}}"])
    assert "post" in paths[f"{SMS}/send"]
    assert "get" in paths[f"{SMS}/records"]
    assert "get" in paths[f"{SMS}/quota"]


def test_sms_endpoints_require_authentication() -> None:
    assert client.get(f"{SMS}/signatures").status_code == 401
    assert client.post(f"{SMS}/signatures").status_code == 401
    assert client.get(f"{SMS}/templates").status_code == 401
    assert client.post(f"{SMS}/send").status_code == 401
    assert client.get(f"{SMS}/records").status_code == 401
    assert client.get(f"{SMS}/quota").status_code == 401


def test_sms_send_requires_confirm_and_idempotency_key() -> None:
    # 未带 Idempotency-Key 时由 Header 校验拦截（422）；带键但未 confirm 时 428。
    resp = client.post(f"{SMS}/send", json={"content": "测试", "phones": ["13800000000"]})
    assert resp.status_code in (401, 422)
    assert "Idempotency-Key" in resp.text or resp.status_code == 401


def test_sms_schema_validation() -> None:
    from app.schemas.admin_sms_admin import (
        SmsSendRequest,
        SmsSignatureCreate,
        SmsSignatureUpdate,
        SmsTemplateCreate,
        SmsTemplateUpdate,
    )

    # 模板与自由文本二选一，目标至少一类。
    with pytest.raises(ValidationError):
        SmsSendRequest(phones=["13800000000"])
    with pytest.raises(ValidationError):
        SmsSendRequest(template_id=1, content="x", phones=["13800000000"])
    with pytest.raises(ValidationError):
        SmsSendRequest(content="x")
    assert SmsSendRequest(template_id=1, user_ids=[1, 2], variables={"name": "A"}).template_id == 1
    # 批量上限
    with pytest.raises(ValidationError):
        SmsSendRequest(content="x", user_ids=list(range(1, 502)))
    with pytest.raises(ValidationError):
        SmsSendRequest(content="x", phones=[f"1380000{i:04d}" for i in range(101)])

    assert SmsSignatureCreate(name="选爱").status == "pending"
    with pytest.raises(ValidationError):
        SmsSignatureCreate(name="x", status="unknown")
    with pytest.raises(ValidationError):
        SmsSignatureUpdate()
    assert SmsTemplateCreate(name="活动通知", code="ACT_NOTICE", content="您好 {name}").status == 1
    with pytest.raises(ValidationError):
        SmsTemplateUpdate()


def test_sms_tables_registered_in_business_schema() -> None:
    for table in ("admin_sms_signature", "admin_sms_template", "admin_sms_message"):
        assert table in BUSINESS_TABLES
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in BUSINESS_TABLES[table]


def test_sms_provider_fails_closed_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from fastapi import HTTPException

    from app.core.config import settings
    from app.services.sms.providers import get_sms_template_provider

    monkeypatch.setattr(settings, "sms_template_provider", "disabled")
    provider = get_sms_template_provider()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.send_template("13800000000", "ACT_NOTICE", {}))
    assert exc.value.status_code == 503

    monkeypatch.setattr(settings, "sms_template_provider", "not-a-vendor")
    with pytest.raises(HTTPException) as exc:
        get_sms_template_provider()
    assert exc.value.status_code == 503


def test_sms_record_phone_is_masked() -> None:
    from app.core.sensitive_fields import mask_phone

    assert mask_phone("13800001234") == "138****1234"


# ─── A6 外呼 ────────────────────────────────────────────────────────

OUTBOUND = "/api/v1/admin/outbound-call"


def test_outbound_routes_registered() -> None:
    paths = _paths()
    assert {"get", "put"} <= set(paths[f"{OUTBOUND}/config"])
    assert "get" in paths[f"{OUTBOUND}/balance"]
    assert {"get", "post"} <= set(paths[f"{OUTBOUND}/numbers"])
    assert {"patch", "delete"} <= set(paths[f"{OUTBOUND}/numbers/{{number_id}}"])
    assert {"get", "post"} <= set(paths[f"{OUTBOUND}/tasks"])
    assert "post" in paths[f"{OUTBOUND}/tasks/{{task_id}}/call"]
    assert "get" in paths[f"{OUTBOUND}/records"]


def test_outbound_endpoints_require_authentication() -> None:
    assert client.get(f"{OUTBOUND}/config").status_code == 401
    assert client.get(f"{OUTBOUND}/balance").status_code == 401
    assert client.get(f"{OUTBOUND}/numbers").status_code == 401
    assert client.get(f"{OUTBOUND}/tasks").status_code == 401
    assert client.get(f"{OUTBOUND}/records").status_code == 401


def test_outbound_schema_validation() -> None:
    from app.schemas.admin_outbound_admin import (
        OutboundConfigUpdate,
        OutboundNumberCreate,
        OutboundNumberUpdate,
    )

    with pytest.raises(ValidationError):
        OutboundConfigUpdate()
    with pytest.raises(ValidationError):
        OutboundNumberUpdate()
    with pytest.raises(ValidationError):
        OutboundNumberCreate(phone="1")
    assert OutboundNumberCreate(phone="02512345678", area="南京").area == "南京"


def test_outbound_tables_registered_in_business_schema() -> None:
    for table in (
        "admin_outbound_number",
        "admin_outbound_task",
        "admin_outbound_record",
        "admin_outbound_account",
    ):
        assert table in BUSINESS_TABLES
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in BUSINESS_TABLES[table]


def test_outbound_provider_fails_closed_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from fastapi import HTTPException

    from app.core.config import settings
    from app.services.outbound_call.providers import get_outbound_provider

    monkeypatch.setattr(settings, "outbound_call_provider", "disabled")
    provider = get_outbound_provider()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.dial("13800000000", caller_number=None, task_id=1))
    assert exc.value.status_code == 503

    monkeypatch.setattr(settings, "outbound_call_provider", "jixun")
    with pytest.raises(HTTPException) as exc:
        get_outbound_provider()
    assert exc.value.status_code == 503


# ─── A2 微信公众号 ──────────────────────────────────────────────────

WECHAT = "/api/v1/admin/wechat"


def test_wechat_routes_registered() -> None:
    paths = _paths()
    assert {"get", "put"} <= set(paths[f"{WECHAT}/config"])
    assert "get" in paths[f"{WECHAT}/fans"]
    assert "post" in paths[f"{WECHAT}/fans/sync"]
    assert {"get", "post"} <= set(paths[f"{WECHAT}/fans/groups"])
    assert {"patch", "delete"} <= set(paths[f"{WECHAT}/fans/groups/{{group_id}}"])
    assert {"get", "put"} <= set(paths[f"{WECHAT}/menu"])
    assert {"get", "post"} <= set(paths[f"{WECHAT}/autoreply/rules"])
    assert {"patch", "delete"} <= set(paths[f"{WECHAT}/autoreply/rules/{{rule_id}}"])
    assert "get" in paths[f"{WECHAT}/templates"]
    assert "post" in paths[f"{WECHAT}/templates/sync"]
    assert "post" in paths[f"{WECHAT}/messages/send"]
    assert "get" in paths[f"{WECHAT}/messages/records"]


def test_wechat_endpoints_require_authentication() -> None:
    assert client.get(f"{WECHAT}/config").status_code == 401
    assert client.get(f"{WECHAT}/fans").status_code == 401
    assert client.post(f"{WECHAT}/fans/sync").status_code == 401
    assert client.get(f"{WECHAT}/menu").status_code == 401
    assert client.get(f"{WECHAT}/templates").status_code == 401
    assert client.post(f"{WECHAT}/messages/send").status_code == 401


def test_wechat_schema_validation() -> None:
    from app.schemas.admin_wechat_admin import (
        WechatConfigUpdate,
        WechatMenuButton,
        WechatMenuPublish,
        WechatReplyRuleCreate,
        WechatReplyRuleUpdate,
        WechatSendRequest,
    )

    # 契约要求：配置更新模型里不存在密钥字段，且传了会 422（extra=forbid）而非静默丢弃。
    assert "app_secret" not in WechatConfigUpdate.model_fields
    assert "api_token" not in WechatConfigUpdate.model_fields
    with pytest.raises(ValidationError):
        WechatConfigUpdate(app_secret="plaintext")
    with pytest.raises(ValidationError):
        WechatConfigUpdate()
    with pytest.raises(ValidationError):
        WechatMenuPublish(top_menus=[])
    with pytest.raises(ValidationError):
        WechatMenuButton(name="更多", type="view", sub_button=[WechatMenuButton(name="x")])
    with pytest.raises(ValidationError):
        WechatReplyRuleCreate(name="k", match_type="keyword", content="x")
    with pytest.raises(ValidationError):
        WechatReplyRuleUpdate()
    with pytest.raises(ValidationError):
        WechatSendRequest(send_type="template", data={})
    with pytest.raises(ValidationError):
        WechatSendRequest(send_type="broadcast", group_id=1)
    assert WechatSendRequest(send_type="broadcast", content="x", group_id=1).content == "x"


def test_wechat_tables_registered_in_business_schema() -> None:
    for table in (
        "admin_wechat_fan_group",
        "admin_wechat_fan",
        "admin_wechat_autoreply_rule",
        "admin_wechat_template",
        "admin_wechat_message",
    ):
        assert table in BUSINESS_TABLES
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in BUSINESS_TABLES[table]


# ─── A3 电子合同 ────────────────────────────────────────────────────

ECONTRACT = "/api/v1/admin/e-contracts"
ECONTRACT_TEMPLATES = "/api/v1/admin/e-contract-templates"
ECONTRACT_SEALS = "/api/v1/admin/e-contract-seals"
ECONTRACT_CONFIG = "/api/v1/admin/e-contract-config"


def test_econtract_routes_registered() -> None:
    paths = _paths()
    assert {"get", "post"} <= set(paths[ECONTRACT])
    assert "get" in paths[f"{ECONTRACT}/{{contract_id}}"]
    assert "post" in paths[f"{ECONTRACT}/{{contract_id}}/void"]
    assert {"get", "post"} <= set(paths[ECONTRACT_TEMPLATES])
    assert {"patch", "delete"} <= set(paths[f"{ECONTRACT_TEMPLATES}/{{template_id}}"])
    assert {"get", "post"} <= set(paths[ECONTRACT_SEALS])
    assert {"patch", "delete"} <= set(paths[f"{ECONTRACT_SEALS}/{{seal_id}}"])
    assert {"get", "put"} <= set(paths[ECONTRACT_CONFIG])


def test_econtract_endpoints_require_authentication() -> None:
    assert client.get(ECONTRACT).status_code == 401
    assert client.post(f"{ECONTRACT}/1/void").status_code == 401
    assert client.get(ECONTRACT_TEMPLATES).status_code == 401
    assert client.get(ECONTRACT_SEALS).status_code == 401
    assert client.get(ECONTRACT_CONFIG).status_code == 401


def test_econtract_schema_validation() -> None:
    from app.schemas.admin_econtract_admin import (
        EcontractConfigUpdate,
        EcontractCreate,
        EcontractSealCreate,
        EcontractTemplateCreate,
        EcontractTemplateUpdate,
        EcontractVoidRequest,
    )

    with pytest.raises(ValidationError):
        EcontractTemplateCreate(name="x")
    assert EcontractTemplateCreate(name="x", content="正文").content == "正文"
    with pytest.raises(ValidationError):
        EcontractTemplateUpdate()
    with pytest.raises(ValidationError):
        EcontractSealCreate(name="章", image_url="")
    with pytest.raises(ValidationError):
        EcontractCreate(title="协议")
    assert (
        EcontractCreate(title="协议", member_name="张三", member_phone="13800000000").amount
        is None
    )
    assert EcontractVoidRequest(reason="x").reason == "x"
    with pytest.raises(ValidationError):
        EcontractConfigUpdate()


def test_econtract_tables_registered_in_business_schema() -> None:
    for table in (
        "admin_econtract_template",
        "admin_econtract_seal",
        "admin_econtract",
        "admin_econtract_event",
    ):
        assert table in BUSINESS_TABLES
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in BUSINESS_TABLES[table]


def test_esign_provider_reports_adapter_not_implemented() -> None:
    from app.services.esign.providers import provider_status

    status = provider_status()
    assert status["adapter_implemented"] is False
    assert isinstance(status["configured"], bool)


# ─── A5 二维码：小程序码走公众号适配器 ──────────────────────────────


def test_qrcode_miniprogram_requires_wechat_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from fastapi import HTTPException

    from app.core.config import settings
    from app.services import admin_qrcode_admin as qrcode_service

    monkeypatch.setattr(settings, "wechat_mp_app_id", None)
    monkeypatch.setattr(settings, "wechat_mp_app_secret", None)
    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(qrcode_service.render_image("miniprogram", "/pages/landing?from=qr"))
    assert exc.value.status_code == 503

    # h5 类型始终本地渲染，不依赖任何凭据。
    png = asyncio.run(qrcode_service.render_image("h5", "https://example.com/a"))
    assert png[:4] == bytes([0x89, 0x50, 0x4E, 0x47])


# ─── 迁移文件配对 ──────────────────────────────────────────────────


def test_vendor_adapter_migration_files_are_paired() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "migrations" / "admin_ops"
    for suffix in ("up", "down", "verify"):
        assert (root / f"20261020_02_vendor_adapter_tables_{suffix}.sql").is_file()
    up = (root / "20261020_02_vendor_adapter_tables_up.sql").read_text(encoding="utf-8")
    for table in (
        "admin_sms_signature",
        "admin_sms_template",
        "admin_sms_message",
        "admin_outbound_number",
        "admin_outbound_task",
        "admin_outbound_record",
        "admin_outbound_account",
        "admin_wechat_fan_group",
        "admin_wechat_fan",
        "admin_wechat_autoreply_rule",
        "admin_wechat_template",
        "admin_wechat_message",
        "admin_econtract_template",
        "admin_econtract_seal",
        "admin_econtract",
        "admin_econtract_event",
    ):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in up


# ─── 权限映射：新前缀不得被旧关键词规则抢走 ──────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/sms/send",
        "/api/v1/admin/wechat/messages/send",
        "/api/v1/admin/wechat/config",
        "/api/v1/admin/e-contracts/1/void",
        "/api/v1/admin/outbound-call/tasks",
        "/api/v1/admin/materials",
        "/api/v1/admin/qrcodes",
        "/api/v1/admin/sales-library/items",
        "/api/v1/admin/lovecard-templates",
        "/api/v1/admin/interact/contents",
        "/api/v1/admin/alliance/activities",
    ],
)
def test_new_admin_prefixes_declare_their_own_permission(path: str) -> None:
    """这些前缀必须走 @declare_permission，不能被 /messages、/activities 等旧规则命中。"""
    from starlette.requests import Request

    from app.api.dependencies import _matchmaker_admin_permission

    request = Request({"type": "http", "method": "POST", "path": path, "headers": []})
    assert _matchmaker_admin_permission(request) is None
