"""AI 测试期用户隔离（``AI_TEST_ONLY_USER_IDS``）的行为测试。

覆盖三层：
1. ``Settings.ai_test_only_user_id_set`` 的解析容错；
2. ``_require_ai_test_scope`` 的判定（空范围放行、范围内放行、范围外/无上下文拒绝）；
3. ``require_ai_feature`` 在其它门禁通过后仍会执行该隔离。
"""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.request_context import current_user_id_context
from app.services.ai.flags import (
    AiFeature,
    AiFeatureDisabledError,
    _require_ai_test_scope,
    require_ai_feature,
)


def _settings(scope: str) -> SimpleNamespace:
    parsed = Settings.model_construct(ai_test_only_user_ids=scope).ai_test_only_user_id_set
    return SimpleNamespace(ai_test_only_user_id_set=parsed)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", frozenset()),
        ("21,22,23,24", frozenset({21, 22, 23, 24})),
        ("21, 22", frozenset({21, 22})),
        ("21；22，23", frozenset({21, 22, 23})),
        ("21,abc,22", frozenset({21, 22})),
        ("  24  ", frozenset({24})),
    ],
)
def test_test_scope_ids_are_parsed_tolerantly(raw: str, expected: frozenset[int]) -> None:
    assert Settings.model_construct(ai_test_only_user_ids=raw).ai_test_only_user_id_set == expected


def test_empty_scope_allows_every_caller() -> None:
    token = current_user_id_context.set(999)
    try:
        _require_ai_test_scope(_settings(""), AiFeature.PROFILE)
    finally:
        current_user_id_context.reset(token)


def test_caller_inside_scope_is_allowed() -> None:
    token = current_user_id_context.set(21)
    try:
        _require_ai_test_scope(_settings("21,22,23,24"), AiFeature.PROFILE)
    finally:
        current_user_id_context.reset(token)


def test_caller_outside_scope_is_rejected() -> None:
    token = current_user_id_context.set(2)
    try:
        with pytest.raises(AiFeatureDisabledError):
            _require_ai_test_scope(_settings("21,22,23,24"), AiFeature.PROFILE)
    finally:
        current_user_id_context.reset(token)


def test_missing_caller_context_is_rejected_when_scope_is_set() -> None:
    """后台任务没有请求上下文，同样要被挡住（fail-closed）。"""
    with pytest.raises(AiFeatureDisabledError):
        _require_ai_test_scope(_settings("21,22,23,24"), AiFeature.PROFILE)


def test_require_ai_feature_applies_scope_after_other_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.ai.flags.is_ai_feature_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("app.services.ai.flags._production_approvals_ok", lambda *_a, **_k: True)

    token = current_user_id_context.set(2)
    try:
        with pytest.raises(AiFeatureDisabledError):
            require_ai_feature(AiFeature.PROFILE, _settings("21,22,23,24"))
    finally:
        current_user_id_context.reset(token)
