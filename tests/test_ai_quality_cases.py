"""FIX-09（AI-07）：合成评测案例集的结构校验。

案例文件 ``scripts/moxiang_prompt_loop/cases/synthetic-24.json`` 是质量评测
基线的数据资产：本测试保证其结构完整（6 类 × 4 例、必填键齐全、禁止输出
非空），真实模型跑分不在这里执行（依赖获批 Provider，NOT_RUN）。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

CASES_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "moxiang_prompt_loop"
    / "cases"
    / "synthetic-24.json"
)

EXPECTED_CATEGORIES = {
    "dual_subject",
    "conditional_update",
    "missing_info",
    "contradictory_info",
    "repeated_confirmation",
    "failure_recovery",
}


def _load() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_cases_file_has_24_cases_across_6_categories() -> None:
    data = _load()
    cases = data["cases"]
    assert len(cases) == 24
    counts = Counter(case["category"] for case in cases)
    assert set(counts) == EXPECTED_CATEGORIES
    assert all(count == 4 for count in counts.values())


def test_each_case_has_required_structure() -> None:
    for case in _load()["cases"]:
        assert case["id"], case
        assert case["category"] in EXPECTED_CATEGORIES, case
        assert case["input"], case
        assert case["expected"], case
        assert case["forbidden"], f"{case['id']} 必须声明禁止输出"
        assert case["scoring"], case


def test_case_ids_are_unique() -> None:
    ids = [case["id"] for case in _load()["cases"]]
    assert len(ids) == len(set(ids))


def test_fixture_references_resolve_to_existing_files() -> None:
    """CLI 与包文档中引用的 transcript fixture 必须真实存在。"""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "moxiang" / "transcripts" / "24turn-portrait-regression.jsonl"
    assert fixture.exists()
