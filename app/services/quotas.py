import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import daily_quota_key, get_daily_used
from app.schemas.quotas import QuotaItem, QuotaSummary
from app.services.admin_config import get_runtime_value
from app.services.membership import get_active_membership_row


async def _membership_rights(db: AsyncSession, user_id: int) -> tuple[bool, dict]:
    row = await get_active_membership_row(db, user_id)
    if not row:
        return False, {}
    value = row["rights"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return True, value if isinstance(value, dict) else {}


async def _extra_remaining(db: AsyncSession, user_id: int, quota_code: str) -> int:
    result = await db.execute(text("SELECT COALESCE(SUM(remaining),0) FROM user_quota_grant WHERE user_id=:user_id AND quota_code=:quota_code AND (expires_at IS NULL OR expires_at>UTC_TIMESTAMP())"), {"user_id": user_id, "quota_code": quota_code})
    return int(result.scalar() or 0)


async def consume_extra(db: AsyncSession, user_id: int, quota_code: str, reason: str, target_user_id: int | None = None) -> bool:
    result = await db.execute(text("SELECT id FROM user_quota_grant WHERE user_id=:user_id AND quota_code=:quota_code AND remaining>0 AND (expires_at IS NULL OR expires_at>UTC_TIMESTAMP()) ORDER BY expires_at IS NULL, expires_at, id LIMIT 1 FOR UPDATE"), {"user_id": user_id, "quota_code": quota_code})
    row = result.first()
    if not row:
        return False
    await db.execute(text("UPDATE user_quota_grant SET remaining=remaining-1 WHERE id=:id"), {"id": row[0]})
    await db.execute(text("INSERT INTO user_quota_usage (user_id,quota_code,quota_date,source,reason,target_user_id) VALUES (:user_id,:quota_code,:quota_date,'points',:reason,:target_user_id)"), {"user_id": user_id, "quota_code": quota_code, "quota_date": date.today(), "reason": reason, "target_user_id": target_user_id})
    return True


async def grant(db: AsyncSession, user_id: int, quota_code: str, amount: int, source: str, order_no: str) -> None:
    await db.execute(text("INSERT INTO user_quota_grant (user_id,quota_code,remaining,source,order_no) VALUES (:user_id,:quota_code,:remaining,:source,:order_no)"), {"user_id": user_id, "quota_code": quota_code, "remaining": amount, "source": source, "order_no": order_no})


async def resolve_browse_limit(
    db: AsyncSession, user_id: int, is_vip: bool | None = None
) -> int:
    """每日可查看的**不同用户**上限。

    会员读套餐权益 ``rights.browse_daily_limit``（缺键回退 20），非会员读平台
    权限快照 ``free_browse_daily_limit``。``discovery._quota_limit`` 与
    ``/users/me/quotas`` 共用此函数，避免"接口报 20、实际只给 8"的分叉。
    """
    vip, rights = await _membership_rights(db, user_id)
    if is_vip is not None:
        vip = is_vip
    if vip:
        value = rights.get("browse_daily_limit")
        return max(0, int(value)) if value is not None else 20
    return int(
        await get_runtime_value(
            db,
            "platform_permissions",
            "free_browse_daily_limit",
            settings.browse_daily_limit,
        )
    )


async def summary(db: AsyncSession, user_id: int) -> QuotaSummary:
    vip, rights = await _membership_rights(db, user_id)
    definitions = (
        ("apply", settings.apply_daily_free_limit + (int(rights.get("apply_bonus") or 0) if vip else 0), "apply"),
        ("browse", await resolve_browse_limit(db, user_id, is_vip=vip), "browse"),
        ("superlike", settings.superlike_daily_vip_limit if vip else settings.superlike_daily_free_limit, "superlike"),
        ("paper_plane", settings.paper_plane_daily_limit, "paper_plane"),
    )
    items: list[QuotaItem] = []
    for quota_code, daily_limit, redis_code in definitions:
        key = daily_quota_key(f"discovery:{redis_code}", user_id)
        if quota_code == "paper_plane":
            key = daily_quota_key("paper-plane", user_id)
        used = await get_daily_used(key)
        daily_remaining = max(0, daily_limit - used)
        extra = await _extra_remaining(db, user_id, quota_code)
        items.append(QuotaItem(quota_code=quota_code, daily_limit=daily_limit, daily_used=used, daily_remaining=daily_remaining, extra_remaining=extra, total_remaining=daily_remaining + extra))
    return QuotaSummary(items=items)
