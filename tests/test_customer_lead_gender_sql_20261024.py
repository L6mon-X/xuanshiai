"""A13-gender：客源 gender 列注入的回归测试（2026-10-24）。

线上 MySQL 1241（``Operand should contain 1 column(s)``）复盘：
旧实现用 ``select_sql.replace("FROM customer_lead", ", CAST(gender ...) FROM customer_lead")``，
而 ``LEAD_SELECT`` 的 ``tags_raw`` 标量子查询里含 ``FROM customer_lead_tag_relation``，
``str.replace`` 会连带命中其前缀子串 ``FROM customer_lead``，把 gender 注入**子查询内部**，
使标量子查询返回两列 → 报错。现改为 ``_apply_gender_column``，用词边界只匹配外层表引用。
"""

from app.services.customer_lead_admin import LEAD_SELECT, _apply_gender_column


def test_gender_injected_exactly_once() -> None:
    sql = _apply_gender_column(LEAD_SELECT)
    assert sql.count("CAST(gender AS SIGNED) AS gender") == 1


def test_gender_not_injected_into_scalar_subquery() -> None:
    sql = _apply_gender_column(LEAD_SELECT)
    tags_start = sql.index("AS tags_raw")
    # 子查询体（FROM customer_lead_tag_relation 那段）绝不能出现 gender
    subquery = sql[sql.index("(SELECT GROUP_CONCAT"): tags_start]
    assert "gender" not in subquery
    # gender 列应落在子查询结束之后的外层 SELECT 列表里
    assert sql.index("CAST(gender AS SIGNED) AS gender") > tags_start


def test_base_select_untouched_without_gender() -> None:
    # 未触发注入时 LEAD_SELECT 本身不含 gender，标量子查询保持单列
    assert "gender" not in LEAD_SELECT
    assert LEAD_SELECT.count("FROM customer_lead_tag_relation") == 1
