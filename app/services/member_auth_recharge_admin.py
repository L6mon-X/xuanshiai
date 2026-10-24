"""会员核验额度「在线充值」（A17）后台服务——充值订单骨架。

真实核验额度由各认证厂商持有，本模块只维护「充值订单」流水，按 provider 分档：
- ``disabled``（默认，厂商未定）：下单 / 回调返回 503，明确未接入，前端保持
  「展示余量 + 联系服务商」弹窗，不伪造支付；套餐目录仍可只读展示。
- ``mock``（仅开发/联调，配置校验禁止出现在 staging/production）：生成待付订单
  + 模拟支付链接；``apply_mock_callback`` 可把 pending 订单置为已付。
- ``real``：预留分支，接入具体厂商后替换 ``_create_provider_order`` 占位实现。

订单落到 `member_auth_recharge_order`（BUSINESS_TABLES 定义 + 迁移镜像）。
额度真正入账（quota_remaining 刷新）由厂商回调对接后再接线，本骨架不参与扣减。
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.member_auth_recharge_admin import QuotaPackage, RechargeOrder

_TABLE = "member_auth_recharge_order"

# 只读套餐目录（骨架阶段内置，后续可迁移到 admin_recharge_item 目录表）。
_PACKAGES: list[QuotaPackage] = [
    QuotaPackage(id="realname_100", kind="realname", name="实名认证 100 次", quantity=100, price=200.00),
    QuotaPackage(id="realname_500", kind="realname", name="实名认证 500 次", quantity=500, price=900.00),
    QuotaPackage(id="realname_1000", kind="realname", name="实名认证 1000 次", quantity=1000, price=1600.00),
    QuotaPackage(id="marriage_100", kind="marriage", name="婚姻核验 100 次", quantity=100, price=300.00),
    QuotaPackage(id="marriage_500", kind="marriage", name="婚姻核验 500 次", quantity=500, price=1350.00),
    QuotaPackage(id="marriage_1000", kind="marriage", name="婚姻核验 1000 次", quantity=1000, price=2400.00),
]

_ORDER_SELECT = (
    "SELECT order_no, kind, package_id, package_name, quantity, unit_price, total_amount, "
    "currency, status, provider, pay_url, created_at, paid_at "
    f"FROM {_TABLE}"
)


def current_provider() -> str:
    return settings.verification_recharge_provider


def list_packages(kind: str | None = None) -> list[QuotaPackage]:
    packages = [pkg for pkg in _PACKAGES if pkg.enabled]
    if kind:
        packages = [pkg for pkg in packages if pkg.kind == kind]
    return packages


def _find_package(package_id: str, kind: str) -> QuotaPackage:
    for pkg in _PACKAGES:
        if pkg.id == package_id and pkg.kind == kind and pkg.enabled:
            return pkg
    raise HTTPException(422, detail="套餐不存在或已下架")


async def _table_ready(db: AsyncSession) -> bool:
    return bool(
        (await db.execute(text(
            "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ), {"t": _TABLE})).scalar()
    )


def _new_order_no() -> str:
    return f"VR{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}{uuid4().hex[:8].upper()}"


def _order_from_row(row: Any) -> RechargeOrder:
    data = dict(row)
    for key in ("unit_price", "total_amount"):
        if data.get(key) is not None:
            data[key] = float(data[key])
    return RechargeOrder(**data)


async def _get_order(db: AsyncSession, order_no: str) -> RechargeOrder:
    row = (await db.execute(text(f"{_ORDER_SELECT} WHERE order_no = :order_no"), {"order_no": order_no})).mappings().first()
    if not row:
        raise HTTPException(404, detail="充值订单不存在")
    return _order_from_row(row)


def _create_provider_order(provider: str, order_no: str, package: QuotaPackage, qty: int) -> tuple[str | None, str | None]:
    """按 provider 生成支付载体，返回 (pay_url, qr_code_url)。"""
    if provider == "mock":
        return (f"https://mock.pay/{order_no}", f"https://mock.pay/qr/{order_no}")
    # real：厂商 SDK 未接入；骨架阶段明确报 501，接入后替换本分支。
    raise HTTPException(501, detail="真实支付厂商尚未接入")


async def create_order(db: AsyncSession, account_id: int, kind: str, package_id: str, qty: int) -> RechargeOrder:
    provider = current_provider()
    if provider == "disabled":
        raise HTTPException(503, detail="核验额度充值尚未开通（厂商未接入）")
    if not await _table_ready(db):
        raise HTTPException(503, detail="充值订单表未就绪：请先执行 A17 迁移")
    package = _find_package(package_id, kind)
    order_no = _new_order_no()
    pay_url, qr_code_url = _create_provider_order(provider, order_no, package, qty)
    total = round(package.price * qty, 2)
    await db.execute(text(f"""INSERT INTO {_TABLE}
        (order_no, kind, package_id, package_name, quantity, unit_price, total_amount, currency, status, provider, pay_url, created_by)
        VALUES (:order_no, :kind, :package_id, :package_name, :quantity, :unit_price, :total_amount, 'CNY', 'pending', :provider, :pay_url, :created_by)"""), {
        "order_no": order_no, "kind": kind, "package_id": package.id, "package_name": package.name,
        "quantity": package.quantity * qty, "unit_price": package.price, "total_amount": total,
        "provider": provider, "pay_url": pay_url, "created_by": account_id,
    })
    await db.execute(text("""INSERT INTO business_audit_log
        (actor_user_id, action, resource_type, resource_id, reason)
        VALUES (:actor, 'member.auth.recharge', 'member_auth_recharge_order', NULL, :reason)"""),
        {"actor": account_id, "reason": f"发起核验额度充值订单 {order_no}"})
    await db.commit()
    return await _get_order(db, order_no)


async def get_order_status(db: AsyncSession, order_no: str) -> RechargeOrder:
    if not await _table_ready(db):
        raise HTTPException(503, detail="充值订单表未就绪：请先执行 A17 迁移")
    return await _get_order(db, order_no)


async def apply_mock_callback(db: AsyncSession, order_no: str, status: str) -> RechargeOrder:
    """支付回调（仅 mock/联调）：pending → paid/failed。real 由厂商签名回调驱动。"""
    if current_provider() != "mock":
        raise HTTPException(503, detail="仅 mock provider 支持手动回调；real 由厂商回调驱动")
    if not await _table_ready(db):
        raise HTTPException(503, detail="充值订单表未就绪：请先执行 A17 迁移")
    await db.execute(text(f"""UPDATE {_TABLE}
        SET status = :status, paid_at = UTC_TIMESTAMP(), updated_at = UTC_TIMESTAMP()
        WHERE order_no = :order_no AND status = 'pending'"""), {"status": status, "order_no": order_no})
    await db.commit()
    order = await _get_order(db, order_no)
    if order.provider != "mock":
        raise HTTPException(409, detail="该订单非 mock 下单，不能手动回调")
    return order
