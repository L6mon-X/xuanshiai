"""学历认证 legacy 入口不得伪造「审核中」。

回归背景（2026-10-24 用户端测试）：「未提交审核材料，点击去认证页面显示审核中」。
根因是 ``PUT /users/me/certifications/education``（legacy JSON 入口）只写学历字段，
却把 ``education_verified`` 直接置 1（= 审核中），后台审核页面对应的
``education_cert`` 为空，无材料可审。

本文件锁定：legacy 入口只保存学历，不推进状态；且已有材料的历史状态不被回退。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.certifications import EducationCertificationRequest
from app.services import certifications as service


class _CapturingDb:
    def __init__(self) -> None:
        self.sql = ""
        self.params: dict = {}
        self.committed = False

    async def execute(self, statement, params=None):
        self.sql = str(statement)
        self.params = dict(params or {})
        return SimpleNamespace(scalar=lambda: None)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_legacy_education_entry_does_not_mark_under_review(monkeypatch) -> None:
    db = _CapturingDb()

    async def _fake_get_certifications(*_args, **_kwargs):
        return "certs"

    monkeypatch.setattr(service, "get_certifications", _fake_get_certifications)

    result = await service.submit_education(
        db, 7, EducationCertificationRequest(education="本科")
    )

    assert result == "certs"
    assert db.committed is True
    assert db.params == {"id": 7, "education": "本科"}
    # 新插入行一律为未提交（0），不再是原先硬编码的 1
    assert "VALUES (:id, :education, 0)" in db.sql
    # 已存在行只在没有材料时才回落到 0，避免把已正式提交的状态打回未提交
    assert "education_verified = CASE" in db.sql
    assert "education_cert IS NULL OR education_cert = ''" in db.sql


@pytest.mark.asyncio
async def test_legacy_education_entry_no_longer_writes_submitted_at(monkeypatch) -> None:
    """没有材料就不能记提交时间，否则审核列表会把它当成待审条目。"""
    db = _CapturingDb()

    async def _fake_get_certifications(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "get_certifications", _fake_get_certifications)

    await service.submit_education(db, 7, EducationCertificationRequest(education="硕士"))

    assert "education_submitted_at" not in db.sql
