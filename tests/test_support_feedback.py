"""C 端反馈 / 意见箱（Q54，2026-11-02）。

锁定：每日上限 429、仅返回本人、图片 JSON 解析、管理端回复置为已回复。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import HTTPException

from app.services import support as service


class _Result:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        scalar: Any = None,
        lastrowid: int = 0,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar
        self.lastrowid = lastrowid

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return dict(self._rows[0]) if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def scalar(self) -> Any:
        return self._scalar


class _Db:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((str(statement), dict(params or {})))
        return self.results.pop(0) if self.results else _Result()

    async def commit(self) -> None:
        return None


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 5,
        "category": "建议",
        "content": "希望增加夜间模式",
        "images_json": json.dumps(["/uploads/a.webp"]),
        "contact_phone": None,
        "status": 0,
        "reply_content": None,
        "replied_at": None,
        "created_at": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_rejects_when_daily_limit_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    async def deny(_key: str, _limit: int) -> bool:
        return False

    monkeypatch.setattr(service, "consume_daily", deny)
    db = _Db()

    with pytest.raises(HTTPException) as error:
        await service.create_feedback(
            db, 7, category="建议", content="x", images=[], contact_phone=None
        )

    assert error.value.status_code == 429
    assert db.calls == []


@pytest.mark.asyncio
async def test_create_persists_images_and_returns_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def allow(_key: str, limit: int) -> bool:
        assert limit == service.DAILY_FEEDBACK_LIMIT
        return True

    monkeypatch.setattr(service, "consume_daily", allow)
    db = _Db(
        _Result(lastrowid=5),            # INSERT user_feedback
        _Result(),                       # business_audit_log
        _Result(rows=[_row()]),          # get_my_feedback
    )

    item = await service.create_feedback(
        db, 7, category="建议", content="希望增加夜间模式", images=["/uploads/a.webp"], contact_phone=None
    )

    assert item.id == 5
    assert item.images == ["/uploads/a.webp"]
    insert_params = db.calls[0][1]
    assert insert_params["user_id"] == 7
    assert json.loads(insert_params["images_json"]) == ["/uploads/a.webp"]
    assert any("support.feedback.create" in sql for sql, _ in db.calls)


@pytest.mark.asyncio
async def test_my_feedback_only_queries_current_user() -> None:
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row()]),
    )

    page = await service.list_my_feedback(db, 7, 1, 20)

    assert page.total == 1
    assert page.has_more is False
    assert len(page.items) == 1
    for sql, params in db.calls:
        assert params.get("user_id") == 7
    assert "WHERE user_id = :user_id" in db.calls[0][0]


@pytest.mark.asyncio
async def test_help_docs_parse_extra_json_and_hide_disabled() -> None:
    db = _Db(
        _Result(scalar=1),
        _Result(
            rows=[
                {
                    "id": 3,
                    "title": "如何认证",
                    "subtitle": "实名与头像",
                    "extra_json": json.dumps({"category": "认证", "body": "上传证件..."}),
                    "updated_at": None,
                }
            ]
        ),
    )

    page = await service.list_help_docs(db, 1, 20)

    assert page.items[0].category == "认证"
    assert page.items[0].body == "上传证件..."
    assert "status = 1" in db.calls[0][0]
    assert "domain = 'help_doc'" in db.calls[0][0]


@pytest.mark.asyncio
async def test_reply_marks_feedback_replied() -> None:
    admin_row = _row(
        status=2,
        reply_content="已记录，感谢反馈",
        replied_by=9,
        nickname="小宣",
        user_id=7,
    )
    db = _Db(
        _Result(rows=[{"id": 5}]),       # SELECT ... FOR UPDATE
        _Result(),                       # UPDATE
        _Result(),                       # business_audit_log
        _Result(rows=[admin_row]),       # get_admin_feedback
    )

    item = await service.reply_feedback(db, 9, 5, "已记录，感谢反馈")

    assert item.status == 2
    assert item.reply_content == "已记录，感谢反馈"
    assert item.replied_by == 9
    assert any("support.feedback.reply" in sql for sql, _ in db.calls)


@pytest.mark.asyncio
async def test_admin_list_applies_status_filter() -> None:
    db = _Db(
        _Result(scalar=0),
        _Result(rows=[]),
    )

    page = await service.list_admin_feedback(
        db, page=1, page_size=20, status=0, category="建议", keyword="夜间"
    )

    assert page.total == 0
    sql, params = db.calls[0]
    assert "f.status = :status" in sql
    assert "f.category = :category" in sql
    assert params["status"] == 0
    assert params["category"] == "建议"
