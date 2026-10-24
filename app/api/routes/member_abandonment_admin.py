"""会员弃海（A9/B3）路由。

静态路径 ``/abandoned``、``/abandonments`` 必须先于 ``/{member_id}`` 系列注册，
因此在 ``app/api/router.py`` 中需排在 ``member_records_admin`` 之前（本文件内部
也按「静态在前」声明）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    CurrentMatchmakerAdmin,
    get_current_matchmaker_admin,
    require_sensitive_operation,
)
from app.db.session import get_db
from app.services.sensitive_operations import (
    abort_sensitive_operation,
    begin_sensitive_operation,
    finish_sensitive_operation,
)
from app.schemas.member_abandonment_admin import (
    AbandonedMemberPage,
    MemberAbandonmentItem,
    MemberAbandonmentPage,
    MemberAbandonRequest,
    MemberBatchAbandonRequest,
    MemberBatchAbandonResult,
    MemberRestoreRequest,
)
from app.services import member_abandonment_admin as service

router = APIRouter(prefix="/admin/members")


def _member_scope(current: CurrentMatchmakerAdmin) -> tuple[str, dict[str, object]]:
    """会员弃海的四档数据范围谓词（与会员列表同一实现，D-16）。"""
    params: dict[str, object] = {}
    scope = current.scope_exists_clause(params, correlation="scope_assignment.user_id = u.id")
    return scope, params


@router.get("/abandoned", response_model=AbandonedMemberPage, summary="弃海会员列表（分页 + 筛选）")
async def abandoned_members(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=64, description="昵称 / 手机号模糊匹配"),
    matchmaker_id: int | None = Query(None, ge=1),
    organization_id: int | None = Query(None, ge=1),
    abandon_type: str | None = Query(None, pattern="^(manual|lead_sync|auto)$"),
    start_date: str | None = Query(None, max_length=10, description="弃海时间起（含）"),
    end_date: str | None = Query(None, max_length=10, description="弃海时间止（含）"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> AbandonedMemberPage:
    current.require("matchmaker.member.read")
    scope, scope_params = _member_scope(current)
    return await service.list_abandoned_members(
        db,
        page,
        page_size,
        search,
        matchmaker_id,
        organization_id,
        abandon_type,
        start_date,
        end_date,
        scope=scope,
        scope_params=scope_params,
    )


@router.get("/abandonments", response_model=MemberAbandonmentPage, summary="弃海记录（分页，含已捞回）")
async def abandonment_records(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False, description="仅看仍在弃海池的记录"),
    abandon_type: str | None = Query(None, pattern="^(manual|lead_sync|auto)$"),
    search: str | None = Query(None, max_length=64, description="昵称 / 手机号模糊匹配"),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberAbandonmentPage:
    current.require("matchmaker.member.read")
    scope, scope_params = _member_scope(current)
    return await service.list_abandonments(
        db, page, page_size, active_only, abandon_type, search, scope=scope, scope_params=scope_params
    )


@router.post(
    "/batch-abandon", response_model=MemberBatchAbandonResult,
    summary="批量弃海（幂等 + 二次确认，一次事务 + 一份审计）",
)
async def member_batch_abandon(
    body: MemberBatchAbandonRequest,
    idempotency_key: str = Depends(require_sensitive_operation),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberBatchAbandonResult:
    """A18：与 batch-status 同构，需 confirm=true + Idempotency-Key；同键重放不重复弃海。"""
    current.require("matchmaker.member.manage")
    # 批量写操作同口径收敛数据范围（D-16）；谓词以 users 为表名，与服务层锁定语句一致。
    scope_params: dict[str, object] = {}
    scope = current.scope_exists_clause(scope_params, correlation="scope_assignment.user_id = users.id")
    reservation, replayed = await begin_sensitive_operation(
        db,
        actor_id=current.account.id,
        operation="matchmaker.member.batch_abandon",
        idempotency_key=idempotency_key,
        payload={"body": body.model_dump(mode="json")},
    )
    if replayed is not None:
        return MemberBatchAbandonResult(**replayed)
    try:
        result = await service.batch_abandon_members(
            db, current.account.id, body, scope=scope, scope_params=scope_params
        )
    except Exception:
        await abort_sensitive_operation(db, reservation)
        raise
    await finish_sensitive_operation(db, reservation, result.model_dump(mode="json"))
    return result


@router.post(
    "/{member_id}/abandon", response_model=MemberAbandonmentItem, status_code=201, summary="放入弃海池"
)
async def member_abandon(
    member_id: int = Path(..., ge=1),
    body: MemberAbandonRequest = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberAbandonmentItem:
    current.require("matchmaker.member.manage")
    scope, scope_params = _member_scope(current)
    return await service.abandon_member(
        db, current.account.id, member_id, body, scope=scope, scope_params=scope_params
    )


@router.post(
    "/{member_id}/restore", response_model=MemberAbandonmentItem, summary="捞取弃海会员（可同时分派红娘）"
)
async def member_restore(
    member_id: int = Path(..., ge=1),
    body: MemberRestoreRequest = ...,
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> MemberAbandonmentItem:
    current.require("matchmaker.member.manage")
    scope, scope_params = _member_scope(current)
    return await service.restore_member(
        db, current.account.id, member_id, body, scope=scope, scope_params=scope_params
    )
