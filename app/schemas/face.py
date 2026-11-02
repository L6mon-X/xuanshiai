"""人脸自助核验契约（Q32，2026-11-02）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FaceVerifyRequest(BaseModel):
    avatar_url: str = Field(
        min_length=1,
        max_length=500,
        description="本人已上传头像的 URL；服务端会与 users.avatar 比对，禁止核验他人图片",
    )


class FaceVerifyResponse(BaseModel):
    verified: bool
    provider: str
    score: float | None = None
    remaining_attempts: int = Field(ge=0, description="今日剩余核验次数")
