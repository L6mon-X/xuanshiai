"""后台账号修改密码接口契约与行为测试。

行为级覆盖（FIX-01）：该接口曾加入权限豁免白名单前的运行时盲区由
``test_admin_permission_coverage`` 静态兜底发现；本文件补运行时行为断言：
匿名 → 401、非后台令牌 → 401、有效后台会话 → 204 且旧密码立即失效、
旧密码错误 → 400、新旧密码相同 → 400。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.dependencies import CurrentMatchmakerAdmin, get_current_matchmaker_admin
from app.api.routes import matchmaker_admin
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.schemas.matchmaker_admin import MatchmakerAdminAccount
from app.services.admin_content import ALLOWED_DOMAINS

client = TestClient(app)

URL = "/api/v1/admin/matchmaker/auth/change-password"
OLD_PASSWORD = "OldPass123"
NEW_PASSWORD = "NewPass456"


def _admin() -> CurrentMatchmakerAdmin:
    return CurrentMatchmakerAdmin(
        account=MatchmakerAdminAccount(
            id=1,
            username="admin",
            display_name="Admin",
            matchmaker_user_id=7,
            data_scope="ALL",
            organization_id=10,
            status=1,
            last_login_at=datetime(2026, 10, 16),
        ),
        session_id=1,
        permissions=frozenset(),
    )


def _db_with_password(stored_plaintext: str) -> AsyncMock:
    db = AsyncMock()
    select_result = MagicMock()
    select_result.mappings.return_value.first.return_value = {
        "password_hash": hash_password(stored_plaintext),
    }
    db.execute = AsyncMock(side_effect=[select_result, MagicMock(), MagicMock()])
    return db


def _override(db: AsyncMock) -> None:
    app.dependency_overrides[get_current_matchmaker_admin] = _admin
    app.dependency_overrides[get_db] = lambda: db


def _clear() -> None:
    app.dependency_overrides.pop(get_current_matchmaker_admin, None)
    app.dependency_overrides.pop(get_db, None)


def test_change_password_route_registered() -> None:
    routes = {
        (route.path, method)
        for route in matchmaker_admin.router.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/admin/matchmaker/auth/change-password", "POST") in routes


def test_missing_content_domains_are_registered() -> None:
    assert {
        "free_pay_item",
        "point_gift",
        "point_exchange",
        "econtract_record",
        "econtract_template",
    } <= ALLOWED_DOMAINS


def test_change_password_anonymous_rejected_401() -> None:
    response = client.post(URL, json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 401


def test_change_password_non_admin_token_rejected_401() -> None:
    # 任意非后台会话令牌（含 C 端用户令牌）无法通过后台令牌解码，按 401 拒绝。
    response = client.post(
        URL,
        json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"Authorization": "Bearer not-a-matchmaker-admin-token"},
    )
    assert response.status_code == 401


def test_change_password_succeeds_and_old_password_invalidated() -> None:
    db = _db_with_password(OLD_PASSWORD)
    _override(db)
    try:
        response = client.post(URL, json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD})
    finally:
        _clear()
    assert response.status_code == 204
    # 第二次 execute 为 UPDATE，新哈希仅能通过新密码校验，旧密码立即失效。
    update_call = db.execute.call_args_list[1]
    new_hash = update_call.args[1]["password_hash"]
    assert verify_password(NEW_PASSWORD, new_hash)
    assert not verify_password(OLD_PASSWORD, new_hash)
    # 第三次 execute 为审计写入，且事务已提交。
    audit_call = db.execute.call_args_list[2]
    assert "admin_account.password.change" in str(audit_call.args[0])
    db.commit.assert_awaited_once()


def test_change_password_wrong_old_password_rejected_400() -> None:
    db = _db_with_password(OLD_PASSWORD)
    _override(db)
    try:
        response = client.post(URL, json={"old_password": "WrongPass999", "new_password": NEW_PASSWORD})
    finally:
        _clear()
    assert response.status_code == 400
    assert response.json()["detail"] == "旧密码不正确"
    db.commit.assert_not_awaited()


def test_change_password_same_password_rejected_400() -> None:
    db = _db_with_password(OLD_PASSWORD)
    _override(db)
    try:
        response = client.post(URL, json={"old_password": OLD_PASSWORD, "new_password": OLD_PASSWORD})
    finally:
        _clear()
    assert response.status_code == 400
    assert response.json()["detail"] == "新密码不能与旧密码相同"
    db.commit.assert_not_awaited()
