"""客源联系方式唯一性守卫回归测试。

历史缺陷：传入 exclude_lead_id 时「id != 自身」被拼进联系方式的 OR 组，
SQL 变成 `... AND (phone = :p OR id != :self)`，任意一条其他有效线索都会被判为占用，
导致恢复弃海客源和编辑客源必然返回 409。
"""

from __future__ import annotations

import sqlite3

import pytest

from app.services.customer_lead_contact import find_conflicting_lead_id


class _StubSession:
    """守卫拼出的是标准 SQL，用 sqlite 内存库真实执行，只验语义不依赖 MySQL。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    async def scalar(self, statement: object, params: dict[str, object]) -> int | None:
        row = self.conn.execute(str(statement), params).fetchone()
        return int(row[0]) if row else None


def _make_session() -> _StubSession:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE customer_lead (id INTEGER PRIMARY KEY, phone TEXT, wechat TEXT, status TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO customer_lead (id, phone, wechat, status) VALUES (?, ?, ?, ?)",
        [
            (1, "13911110001", "wx_lemon", "NEW"),
            (2, "13911110002", "wx_wangxia", "CONTACTED"),
            (6, "13911110006", "wx_sunhao", "LOST"),
            (19, "13922223333", "wx_demo_linyi", "LOST"),
        ],
    )
    return _StubSession(conn)


@pytest.mark.asyncio
async def test_restore_without_any_duplicate_passes() -> None:
    # 弃海线索 19 的联系方式没有被其他有效线索使用，必须放行。
    assert await find_conflicting_lead_id(
        _make_session(), "13922223333", "wx_demo_linyi", exclude_lead_id=19
    ) is None


@pytest.mark.asyncio
async def test_active_lead_sharing_phone_is_reported() -> None:
    session = _make_session()
    assert await find_conflicting_lead_id(session, "13911110001", None, exclude_lead_id=19) == 1
    assert await find_conflicting_lead_id(session, None, "wx_wangxia", exclude_lead_id=19) == 2


@pytest.mark.asyncio
async def test_lost_lead_does_not_occupy_contact() -> None:
    assert await find_conflicting_lead_id(_make_session(), "13911110006", None, exclude_lead_id=19) is None


@pytest.mark.asyncio
async def test_blank_contacts_skip_the_query() -> None:
    assert await find_conflicting_lead_id(_make_session(), "   ", "", exclude_lead_id=19) is None
