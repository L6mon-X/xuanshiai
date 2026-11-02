"""删除评论必须级联子回复（2026-11-02，Q75）。

修复前：``delete_comment`` 只软删父评论，而列表查询刻意保留「有子回复的已删
父节点」，于是用户删掉评论、刷新后又看到它连同下面的回复。本文件锁定级联范围：

- 删除目标评论本身；
- ``root_id`` 指向它的所有后代（嵌套回复）；
- ``parent_id`` 指向它的直接回复（兼容 root_id 为空的历史数据）。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services import community


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return dict(self._row) if self._row else None


class _Db:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.committed = False

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((str(statement), dict(params or {})))
        return self.results.pop(0) if self.results else _Result()

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_delete_comment_cascades_to_descendants() -> None:
    db = _Db(_Result({"post_id": 3}), _Result(), _Result())

    await community.delete_comment(db, user_id=7, comment_id=11)

    comment_updates = [
        (statement, params)
        for statement, params in db.calls
        if "UPDATE community_comment" in statement
    ]
    assert len(comment_updates) == 1
    statement, update_params = comment_updates[0]
    assert "root_id = :comment_id" in statement, "嵌套回复必须一起软删"
    assert "parent_id = :comment_id" in statement, "root_id 为空的历史数据也要覆盖"
    assert "deleted_at IS NULL" in statement, "已删记录不重复写，避免更新时间漂移"
    assert update_params == {"comment_id": 11}
    assert db.committed is True


@pytest.mark.asyncio
async def test_delete_missing_comment_is_404() -> None:
    from fastapi import HTTPException

    db = _Db(_Result(None))

    with pytest.raises(HTTPException) as error:
        await community.delete_comment(db, user_id=7, comment_id=11)

    assert error.value.status_code == 404
