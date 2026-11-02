"""管理端用户反馈列表与回复（Q54，2026-11-02）。

读走 ``matchmaker.system.read``，回复走 ``matchmaker.system.manage``，
并复用 ``require_sensitive_operation``（Idempotency-Key + confirm=true）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentMatchmakerAdmin,
    declare_permission,
    get_current_matchmaker_admin,
    require_sensitive_operation,
)
from app.db.session import get_db
from app.schemas.support import AdminFeedbackItem, AdminFeedbackPage, AdminFeedbackReply
from app.services import support as service
from app.services.sensitive_operations import (
    abort_sensitive_operation,
    begin_sensitive_operation,
    finish_sensitive_operation,
)

router = APIRouter(prefix="/admin/user-feedback")


@declare_permission("matchmaker.system.read")
@router.get("", response_model=AdminFeedbackPage, summary="用户反馈列表")
async def list_feedback(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: int | None = Query(None, ge=0, le=3, description="0待处理 / 1处理中 / 2已回复 / 3已关闭"),
    category: str | None = Query(None, max_length=16),
    keyword: str | None = Query(None, max_length=64),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminFeedbackPage:
    current.require("matchmaker.system.read")
    return await service.list_admin_feedback(
        db,
        page=page,
        page_size=page_size,
        status=status,
        category=category,
        keyword=keyword,
    )


@declare_permission("matchmaker.system.manage")
@router.post("/{feedback_id}/reply", response_model=AdminFeedbackItem, summary="回复用户反馈")
async def reply_feedback(
    feedback_id: int = Path(..., ge=1),
    body: AdminFeedbackReply = ...,
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminFeedbackItem:
    current.require("matchmaker.system.manage")
    reservation, replayed = await begin_sensitive_operation(
        db,
        actor_id=current.account.id,
        operation="admin.user_feedback.reply",
        idempotency_key=idempotency_key,
        payload={"feedback_id": feedback_id, **body.model_dump(mode="json")},
    )
    if replayed is not None:
        return AdminFeedbackItem.model_validate(replayed)
    try:
        item = await service.reply_feedback(
            db, current.account.id, feedback_id, body.reply_content
        )
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    await finish_sensitive_operation(db, reservation, item.model_dump(mode="json"))
    return item
