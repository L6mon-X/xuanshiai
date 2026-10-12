"""后台筛选参数契约回归（D-23）。

背景：2026-09-12 `84b8ff9 fix(M9)` 修过一次 `finance.orders` 日期 query 422 故障——
前端清空日期筛选会发送 `?start_date=`（空字符串），严格 `pattern` 会 422 打挂整个列表页。
2026-10-11 上游 `6de37dc` 又把同一写法带回了 `finance.py`（并新增 8 处到
`customer_leads_admin` / `matchmaker_crm_admin`），说明**只有 finance 一个模块被契约测试守住**
是不够的。

本模块把该契约提升为**全部后台路由模块**的静态检查：

1. 日期类 query 参数不得使用严格 `pattern=r"^\\d{4}-\\d{2}-\\d{2}$"`；
2. `LEGACY_STRICT_DATE_MODULES` 为历史遗留白名单（既有代码、无测试覆盖，待排期整改），
   白名单外的任何模块出现该写法都会失败——防止同类回归再次滑入。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parent.parent / "app" / "api" / "routes"

# 严格日期 pattern 的源码字面量。两种写法都要堵：
#   pattern=r"^\d{4}-\d{2}-\d{2}$"            （内联）
#   _DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"     （常量复用，如 partner_admin.py）
DATE_PATTERN_LITERAL = r"^\d{4}-\d{2}-\d{2}$"

# 内联写法（finance 契约断言的准确形态）。
STRICT_DATE_PATTERN = 'pattern=r"^\\d{4}-\\d{2}-\\d{2}$"'

# 历史遗留模块：仅作冻结标注，不新增；整改计划见
# docs/全项目后端详细修改方案清单-2026-10-12.md 待确认项 11 / D-23。
LEGACY_STRICT_DATE_MODULES: frozenset[str] = frozenset(
    {
        "activity_admin.py",
        "meeting.py",
        "member_follow_up_admin.py",
        "merchant_admin.py",
        "offline_vip_admin.py",
        "partner_admin.py",
        "promoter_staff_admin.py",
    }
)


def _route_modules() -> list[Path]:
    return sorted(p for p in ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


def test_route_modules_found() -> None:
    """守卫测试本身：确保扫描到了路由模块，避免路径写错导致空跑。"""
    modules = _route_modules()
    assert len(modules) >= 50, f"仅扫描到 {len(modules)} 个路由模块，路径可能不对"


def test_no_new_module_uses_strict_date_pattern() -> None:
    """白名单之外的模块不得出现严格日期 pattern（D-23 核心断言）。"""
    offenders: list[str] = []
    for path in _route_modules():
        if path.name in LEGACY_STRICT_DATE_MODULES:
            continue
        source = path.read_text(encoding="utf-8")
        if DATE_PATTERN_LITERAL in source:
            offenders.append(path.name)
    assert not offenders, (
        "以下路由模块新增了严格日期 query pattern，前端传空字符串会触发 422；"
        "请改用 `max_length=10` 并在服务层用 `if <param>:` 判空："
        f"{sorted(offenders)}"
    )


def test_legacy_whitelist_is_accurate() -> None:
    """白名单必须与实际遗留情况一致（修好后应从白名单移除，避免长期挂着）。"""
    stale: list[str] = []
    for name in sorted(LEGACY_STRICT_DATE_MODULES):
        path = ROUTES_DIR / name
        if not path.exists():
            stale.append(f"{name}（文件不存在，应删除白名单项）")
            continue
        if DATE_PATTERN_LITERAL not in path.read_text(encoding="utf-8"):
            stale.append(f"{name}（已无严格 pattern，应移除白名单项）")
    assert not stale, "日期参数白名单已过期，请同步更新：\n" + "\n".join(stale)


def test_finance_uses_lenient_max_length() -> None:
    """finance 是回归重灾区，必须保持宽松写法（沿用既有契约断言）。"""
    from app.api.routes import finance as finance_routes

    src = inspect.getsource(finance_routes)
    assert STRICT_DATE_PATTERN not in src, "finance routes 仍使用严格日期 pattern"
    assert "max_length=10" in src, "finance routes 应当改用 max_length=10 替代 pattern"


def test_legacy_pattern_literal_matches_current_source() -> None:
    """白名单里的模块确实使用了我们监控的那种写法（防止断言字符串漂移）。"""
    for name in sorted(LEGACY_STRICT_DATE_MODULES):
        path = ROUTES_DIR / name
        if not path.exists():
            pytest.skip(f"{name} 不存在")
        assert DATE_PATTERN_LITERAL in path.read_text(encoding="utf-8"), (
            f"{name} 未匹配到监控中的严格 pattern 字面量，请核对断言字符串"
        )
