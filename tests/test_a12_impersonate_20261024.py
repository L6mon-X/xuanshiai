"""A12-模拟登录（受限短时只读 token + 二次确认 + 审计）回归测试（2026-10-24）。

口径：不改变普通登录；模拟会话只读、短时（默认 15 分钟）、可审计。
覆盖：
1. Token 声明：create_token(extra={'imp': 管理员 id}) 编入 imp；
   impersonation_admin_id 能从令牌解出发起管理员 id，普通令牌/无效令牌返回 None。
2. 只读守卫：CurrentUser 带 impersonated_by；get_current_user 从 imp 声明回填；
   app/main.py 注册了拦截写方法的只读中间件。
3. 会话服务：目标不存在 404、status!=1 拒绝；有列写 impersonated_by、缺列降级不写；
   审计写 admin.impersonate.create。
4. 迁移三件套 + 旧库幂等补齐镜像存在。
5. 路由挂载 /admin/members/{member_id}/impersonate（敏感写 + declare_permission）。

假会话沿用项目 StubDB/StubResult 范式，无需真实数据库。
"""

from __future__ import annotations

import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from app.api.dependencies import CurrentUser
from app.api.routes import member_vip_admin
from app.core.security import create_token, impersonation_admin_id
from app.services.auth import create_impersonation_session

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_DIR = REPO_ROOT / "migrations" / "user_impersonate"


class _Result:
    def __init__(self, *, first=None, all_rows=(), lastrowid=0):
        self._first = first
        self._all = list(all_rows)
        self.lastrowid = lastrowid

    def first(self):
        return self._first

    def all(self):
        return self._all

    def mappings(self):
        return self

    def scalar(self):
        return self._first


class _StubDB:
    def __init__(self, results=None):
        self.statements: list[tuple[str, dict]] = []
        self._results = list(results or [])
        self.commits = 0

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))
        if self._results:
            return self._results.pop(0)
        return _Result()

    async def commit(self):
        self.commits += 1


# --------------------------------------------------------------------------- #
# 1. Token 声明
# --------------------------------------------------------------------------- #


def test_create_token_extra_imp_is_decodable() -> None:
    token = create_token(123, 456, "access", timedelta(minutes=15), extra={"imp": 9})
    assert impersonation_admin_id(token) == 9


def test_normal_token_has_no_impersonation_claim() -> None:
    token = create_token(123, 456, "access", timedelta(minutes=60))
    assert impersonation_admin_id(token) is None


def test_invalid_token_impersonation_probe_is_none() -> None:
    assert impersonation_admin_id("not-a-jwt") is None


# --------------------------------------------------------------------------- #
# 2. 只读守卫
# --------------------------------------------------------------------------- #


def test_currentuser_has_impersonated_by_default_none() -> None:
    cu = CurrentUser(id=1, session_id=2, phone=None, status=1, realname_status=0)
    assert cu.impersonated_by is None


def test_get_current_user_reads_imp_claim() -> None:
    from app.api import dependencies

    source = inspect.getsource(dependencies.get_current_user)
    assert 'payload.get("imp")' in source
    assert "impersonated_by=impersonated_by" in source


def test_app_registers_impersonation_readonly_middleware() -> None:
    # 直接读源文件文本，避免 import app.main 触发 create_app() 副作用。
    main_source = (REPO_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "enforce_impersonation_readonly" in main_source
    assert '"POST", "PUT", "PATCH", "DELETE"' in main_source
    assert "impersonation_admin_id" in main_source


# --------------------------------------------------------------------------- #
# 3. 会话服务
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_impersonation_writes_column_when_present() -> None:
    db = _StubDB([
        _Result(first={"id": 5, "status": 1}),   # 目标用户存在且可用
        _Result(first=(1,)),                     # impersonated_by 列存在
        _Result(lastrowid=777),                  # INSERT user_session
        _Result(),                               # UPDATE access_token_hash
        _Result(),                               # INSERT audit
    ])
    result = await create_impersonation_session(db, 9, 5, "1.2.3.4", "pytest-agent")
    assert result["read_only"] is True
    assert result["impersonated_by"] == 9
    assert result["session_id"] == 777
    assert result["expires_in"] == 15 * 60
    insert_stmt = next(sql for sql, _ in db.statements if "INSERT INTO user_session" in sql)
    assert "impersonated_by" in insert_stmt
    assert any("admin.impersonate.create" in sql for sql, _ in db.statements)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_impersonation_skips_column_when_missing() -> None:
    db = _StubDB([
        _Result(first={"id": 5, "status": 1}),   # 目标用户存在
        _Result(first=None),                     # 缺列（迁移未执行）→ 降级
        _Result(lastrowid=888),                  # INSERT user_session
        _Result(),
        _Result(),
    ])
    result = await create_impersonation_session(db, 9, 5, None, None)
    insert_stmt = next(sql for sql, _ in db.statements if "INSERT INTO user_session" in sql)
    assert "impersonated_by" not in insert_stmt
    assert result["session_id"] == 888


@pytest.mark.asyncio
async def test_impersonation_rejects_unavailable_user() -> None:
    db = _StubDB([_Result(first={"id": 5, "status": 2})])  # status!=1
    with pytest.raises(Exception) as exc:
        await create_impersonation_session(db, 9, 5, None, None)
    assert getattr(exc.value, "status_code", None) in {409, 403}


@pytest.mark.asyncio
async def test_impersonation_rejects_missing_user() -> None:
    db = _StubDB([_Result(first=None)])
    with pytest.raises(Exception) as exc:
        await create_impersonation_session(db, 9, 404, None, None)
    assert getattr(exc.value, "status_code", None) == 404


# --------------------------------------------------------------------------- #
# 4. 迁移三件套
# --------------------------------------------------------------------------- #


def test_impersonate_migration_triplet_exists() -> None:
    up = (MIGRATION_DIR / "20261024_01_user_session_impersonated_by_up.sql").read_text(encoding="utf-8")
    down = (MIGRATION_DIR / "20261024_01_user_session_impersonated_by_down.sql").read_text(encoding="utf-8")
    verify = (MIGRATION_DIR / "20261024_01_user_session_impersonated_by_verify.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN" in up and "impersonated_by" in up and "ALTER TABLE `user_session`" in up
    assert "DROP COLUMN `impersonated_by`" in down
    assert "impersonated_by" in verify


# --------------------------------------------------------------------------- #
# 5. 路由挂载
# --------------------------------------------------------------------------- #


def test_impersonate_route_registered_with_permission_and_sensitive() -> None:
    source = inspect.getsource(member_vip_admin)
    assert '"/{member_id}/impersonate"' in source
    assert 'declare_permission("matchmaker.member.impersonate")' in source
    assert 'require("matchmaker.member.impersonate")' in source
    assert "create_impersonation_session" in source
    assert "begin_sensitive_operation" in source
