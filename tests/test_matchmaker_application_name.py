"""红娘/合伙人申请的真实姓名校验。

回归背景（2026-10-24 用户端测试）：「没有设置真实姓名验证，姓名直接填 111 也会成功」。
原实现只校验手机号与 ``realname_status == 2``，对表单里的 ``real_name`` 不做任何
校验就直接入库，导致审核数据不可信。

本文件锁定三条边界：
1. 与实名认证姓名不一致 → 422；
2. 实名库无姓名记录时退回中文格式校验，``111`` 被拒；
3. 与实名一致时放行（不被误伤，含少数民族「·」姓名）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.dependencies import CurrentUser
from app.schemas.auth import MatchmakerApplicationCreate
from app.services import identity as service


class _ReachedDownstream(Exception):
    """哨兵：姓名校验已通过，进入后续申请流程。"""


class _NameLookupDb:
    def __init__(self, verified_name: str | None) -> None:
        self._verified_name = verified_name
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(scalar=lambda: self._verified_name)
        raise _ReachedDownstream


def _current() -> CurrentUser:
    return CurrentUser(
        id=7,
        session_id=1,
        phone="13800138000",
        status=1,
        realname_status=2,
    )


def _request(real_name: str) -> MatchmakerApplicationCreate:
    return MatchmakerApplicationCreate(
        application_type="service_matchmaker",
        real_name=real_name,
        phone="13800138000",
        intro="有多年婚恋服务经验，希望入驻平台为会员牵线。",
    )


@pytest.mark.asyncio
async def test_rejects_name_not_matching_realname_record() -> None:
    db = _NameLookupDb("张三")

    with pytest.raises(HTTPException) as exc_info:
        await service.create_matchmaker_application(db, _current(), _request("111"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "填写的姓名与实名认证信息不一致"


@pytest.mark.asyncio
async def test_rejects_non_chinese_name_when_realname_record_missing() -> None:
    db = _NameLookupDb(None)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_matchmaker_application(db, _current(), _request("111"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "真实姓名需为 2 至 20 位中文"


@pytest.mark.asyncio
async def test_allows_matching_name() -> None:
    db = _NameLookupDb("张三")

    with pytest.raises(_ReachedDownstream):
        await service.create_matchmaker_application(db, _current(), _request("张三"))


@pytest.mark.asyncio
async def test_allows_ethnic_name_with_middle_dot() -> None:
    """实名库无记录时，少数民族姓名的「·」不应被格式校验误伤。"""
    db = _NameLookupDb(None)

    with pytest.raises(_ReachedDownstream):
        await service.create_matchmaker_application(
            db, _current(), _request("买买提·艾力")
        )


@pytest.mark.asyncio
async def test_still_requires_phone_and_realname_status() -> None:
    """原有 403 门禁不能被新校验削弱。"""
    db = _NameLookupDb("张三")
    current = CurrentUser(
        id=7, session_id=1, phone="13800138000", status=1, realname_status=1
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_matchmaker_application(db, current, _request("张三"))

    assert exc_info.value.status_code == 403
    assert db.calls == 0
