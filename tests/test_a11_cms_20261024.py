"""A11-CMS（系统更新公告 / 使用帮助文档，复用 admin_content 不新建表）回归测试（2026-10-24）。

口径：轻量 CRUD，标题落 title、正文/分类落 extra_json；权限沿用 platform.config.*。
覆盖：
1. admin_content 受理新域 update_report / help_doc，并支持 category 过滤与 get_item 详情。
2. admin_cms 薄路由前缀对齐前端（/admin/update-reports、/admin/help-docs），委托 admin_content。
3. router 已注册两个子路由。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.api.routes import admin_cms
from app.services import admin_content

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_admin_content_accepts_new_domains() -> None:
    source = inspect.getsource(admin_content)
    assert "update_report" in source
    assert "help_doc" in source
    assert "category" in source          # EXTRA_FILTER_KEYS 支持按分类筛选
    assert "def get_item" in source       # 详情读取


def test_cms_router_prefixes_match_frontend() -> None:
    assert admin_cms.update_report_router.prefix == "/admin/update-reports"
    assert admin_cms.help_doc_router.prefix == "/admin/help-docs"


def test_cms_routes_delegate_to_content_service() -> None:
    source = inspect.getsource(admin_cms)
    assert "list_items" in source and "create_item" in source and "update_item" in source
    assert "delete_item" in source and "get_item" in source
    # 权限口径：读 platform.config.read，写 platform.config.write
    assert 'require("platform.config.read")' in source
    assert 'require("platform.config.write")' in source


def test_router_registers_cms_routers() -> None:
    router_source = (REPO_ROOT / "app" / "api" / "router.py").read_text(encoding="utf-8")
    assert "admin_cms.update_report_router" in router_source
    assert "admin_cms.help_doc_router" in router_source
