"""情感实验室（MBTI）路由。

- ``PUT /emotion-lab/profile-source``：把端侧测出的结果同步进资料（E1.5）。
- ``GET  /emotion-lab/matches``：合拍的人，算法与首页卡片同源（此前前端走 mock）。

前端 ``api/emotionLab.uts`` 已按这两个路径与 camelCase 出入参写好，因此本模块
落地后前端不需要改路径。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.emotion_lab import (
    EmotionLabMatchesResponse,
    EmotionLabProfileSourceRequest,
    EmotionLabProfileSourceResponse,
)
from app.services.emotion_lab import matches, sync_profile_source

router = APIRouter()


@router.put(
    "/emotion-lab/profile-source",
    response_model=EmotionLabProfileSourceResponse,
    summary="同步情感实验室 MBTI 结果到个人资料",
)
async def put_profile_source(
    body: EmotionLabProfileSourceRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionLabProfileSourceResponse:
    return await sync_profile_source(db, current.id, body)


@router.get(
    "/emotion-lab/matches",
    response_model=EmotionLabMatchesResponse,
    summary="查询与当前用户最合拍的人",
)
async def get_matches(
    limit: int = Query(6, ge=1, le=20, description="返回条数上限"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmotionLabMatchesResponse:
    return await matches(db, current.id, limit)
