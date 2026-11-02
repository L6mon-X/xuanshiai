"""情感实验室「合拍的人」（2026-11-02，Q44）。

修复前：前端 ``EMOTION_LAB_USE_MOCK = true`` 直接返回写死的两个人（70%/68%），
后端只有 profile-source 一个路由。本文件锁定新接口的行为契约：

- 自身 MBTI 为空 → 200 + 空列表 + 可展示提示（不是 404，前端才好出空态）；
- 有 MBTI → 复用 ``discovery.emotion_lab_matches``（即首页卡片合拍度算法）；
- 无候选人 → 仍 200，hint 说明原因；
- 响应按 camelCase 序列化，与前端 ``api/emotionLab.uts`` 既有写法一致。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from app.services import emotion_lab as service


class _Mappings:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _Mappings:
        return self

    def first(self) -> dict[str, Any] | None:
        return dict(self._row) if self._row else None


class _Db:
    def __init__(self, *rows: dict[str, Any] | None) -> None:
        self.rows = list(rows)

    async def execute(self, *_args: object, **_kwargs: object) -> _Mappings:
        return _Mappings(self.rows.pop(0) if self.rows else None)


@pytest.mark.asyncio
async def test_missing_profile_returns_404() -> None:
    with pytest.raises(HTTPException) as error:
        await service.matches(_Db(None), 7)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_without_mbti_returns_hint_not_error() -> None:
    response = await service.matches(_Db({"mbti": None, "updated_at": None}), 7)

    assert response.items == []
    assert response.hint is not None
    assert "MBTI" in response.hint


@pytest.mark.asyncio
async def test_matches_are_ranked_and_serialized(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, int] = {}

    async def fake_rank(_db: Any, user_id: int, limit: int) -> list[dict[str, Any]]:
        captured["user_id"] = user_id
        captured["limit"] = limit
        return [
            {
                "user_id": 22,
                "nickname": "小乙",
                "avatar": "https://cdn.example.com/a.webp",
                "mbti": "ENFP",
                "match_percent": 92,
                "match_reason": "性格互补、作息一致",
            }
        ]

    monkeypatch.setattr(service, "_rank_matches", fake_rank)

    response = await service.matches(_Db({"mbti": "INTJ", "updated_at": None}), 7, limit=6)

    assert captured == {"user_id": 7, "limit": 6}
    assert len(response.items) == 1
    dumped = response.items[0].model_dump(by_alias=True)
    assert dumped["userId"] == 22
    assert dumped["matchPercent"] == 92
    assert dumped["matchReason"] == "性格互补、作息一致"
    assert response.hint is None


@pytest.mark.asyncio
async def test_empty_pool_has_explanatory_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_rank(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(service, "_rank_matches", fake_rank)

    response = await service.matches(_Db({"mbti": "INTJ", "updated_at": None}), 7)

    assert response.items == []
    assert response.hint is not None


def test_route_is_registered() -> None:
    import warnings

    warnings.filterwarnings("ignore")
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/emotion-lab/matches" in paths
    assert "get" in paths["/api/v1/emotion-lab/matches"]
