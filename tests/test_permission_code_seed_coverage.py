"""D-17 回归：所有被引用的后台权限码必须已登记菜单种子。

历史缺陷：`merchant.*` / `commission.*` / `reward.*` / `matchmaker.apportion.*` /
`meeting.feedback.read` 等权限码被 URL 权限映射与 `@declare_permission` / `require()`
引用，但从未写入 `admin_menu` 种子表。结果是这些接口**只有 `*` 超管可用**，
普通后台账号配置了对应权限也必然 403。

验收口径（见 docs/全项目后端详细修改方案清单-2026-10-12.md D-17）：
`{代码引用的权限码} ⊆ {admin_menu 种子登记的权限码}`。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
SEED_FILE = REPO_ROOT / "database_setup_marriage.py"
DEPENDENCIES_FILE = APP_DIR / "api" / "dependencies.py"

PERMISSION_MAP_FUNC = "_matchmaker_admin_permission"
# 权限码形态：小写点分标识符，至少一段点号（如 matchmaker.member.read）。
CODE_RE = re.compile(r'^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$')
ADMIN_MENU_INSERT_RE = re.compile(
    r"INSERT IGNORE INTO admin_menu\b(.*?)\"\"\"", re.S
)


def _referenced_permission_codes() -> set[str]:
    """代码侧引用的全部权限码（装饰器 / require / URL 映射）。"""
    codes: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        codes |= set(re.findall(r'declare_permission\(\s*"([^"]+)"', source))
        codes |= set(re.findall(r'require(?:_any)?\(\s*"([^"]+)"', source))
    codes |= _url_mapping_codes()
    return {code for code in codes if CODE_RE.match(code)}


def _url_mapping_codes() -> set[str]:
    """`_matchmaker_admin_permission` 返回的权限码（按函数体 AST 精确取字符串）。"""
    source = DEPENDENCIES_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    codes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == PERMISSION_MAP_FUNC:
            segment = ast.get_source_segment(source, node) or ""
            codes |= set(re.findall(r'"([a-z][a-z_]*\.[a-z_.]+)"', segment))
    assert codes, f"未从 {PERMISSION_MAP_FUNC} 提取到权限码，断言逻辑可能已失效"
    return codes


def _seeded_permission_codes() -> set[str]:
    """`admin_menu` 种子登记的权限码。"""
    source = SEED_FILE.read_text(encoding="utf-8")
    blocks = ADMIN_MENU_INSERT_RE.findall(source)
    assert blocks, "未找到 admin_menu 种子 INSERT 语句"
    codes: set[str] = set()
    for block in blocks:
        codes |= {code for code in re.findall(r"'([^']+)'", block) if CODE_RE.match(code)}
    return codes


def test_seed_contains_all_referenced_permission_codes() -> None:
    used = _referenced_permission_codes()
    seeded = _seeded_permission_codes()
    missing = sorted(used - seeded)
    assert not missing, (
        "以下权限码被代码引用但未登记 admin_menu 种子，普通后台账号访问必 403；"
        "请在 database_setup_marriage.py 的 admin_menu INSERT 中补齐：\n  "
        + "\n  ".join(missing)
    )


def test_extraction_is_not_vacuous() -> None:
    """守卫：确保两端都提取到足量权限码，避免正则失效导致测试空跑。"""
    assert len(_referenced_permission_codes()) >= 30
    assert len(_seeded_permission_codes()) >= 30


def test_meeting_feedback_permission_registered() -> None:
    """D-17 点名项：`meeting.feedback.read` 必须已登记（此前非超管必 403）。"""
    assert "meeting.feedback.read" in _seeded_permission_codes()


def test_merchant_and_commission_permissions_registered() -> None:
    """D-17 点名项：商家 / 佣金 / 奖励 / 分派四组权限码必须已登记。"""
    seeded = _seeded_permission_codes()
    for code in (
        "merchant.read",
        "merchant.manage",
        "commission.read",
        "commission.write",
        "reward.read",
        "reward.write",
        "matchmaker.apportion.read",
        "matchmaker.apportion.write",
    ):
        assert code in seeded, f"{code} 未登记"
