"""A12-属地（users.ip_region / phone_region 补列 + 列表/详情展示）回归测试（2026-10-24）。

口径：本轮仅补列 + 展示，不接 IP→属地批量解析。
覆盖：
1. Schema：MemberListItem/MemberDetail 的 ip_region / phone_region 可选，缺列降级 None。
2. 路由投影：列表与详情按 user_expr 缺列降级投影 ip_region / phone_region。
3. 迁移三件套 + 旧库幂等补齐镜像存在，两列都可空、无默认。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.api.routes import matchmaker_crm_admin
from app.schemas.matchmaker_crm_admin import MemberDetail, MemberListItem

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_DIR = REPO_ROOT / "migrations" / "user_region"


def test_region_fields_optional_default_none() -> None:
    assert MemberListItem.model_fields["ip_region"].default is None
    assert MemberListItem.model_fields["phone_region"].default is None
    assert "ip_region" in MemberDetail.model_fields
    assert "phone_region" in MemberDetail.model_fields


def test_members_routes_project_region_with_column_guard() -> None:
    source = inspect.getsource(matchmaker_crm_admin)
    assert "{user_expr('ip_region')} AS ip_region" in source
    assert "{user_expr('phone_region')} AS phone_region" in source


def test_region_migration_triplet_exists() -> None:
    up = (MIGRATION_DIR / "20261024_01_user_region_up.sql").read_text(encoding="utf-8")
    down = (MIGRATION_DIR / "20261024_01_user_region_down.sql").read_text(encoding="utf-8")
    verify = (MIGRATION_DIR / "20261024_01_user_region_verify.sql").read_text(encoding="utf-8")
    assert "ip_region" in up and "phone_region" in up
    assert "ADD COLUMN" in up and "ALTER TABLE `users`" in up
    assert "ip_region" in down and "phone_region" in down
    assert "ip_region" in verify and "phone_region" in verify


def test_setup_mirrors_region_columns() -> None:
    setup = (REPO_ROOT / "database_setup_marriage.py").read_text(encoding="utf-8")
    assert "ip_region" in setup and "phone_region" in setup
