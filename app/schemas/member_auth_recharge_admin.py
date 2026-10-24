"""会员认证「核验额度在线充值」（A17）接口契约。

真实核验额度的扣减 / 结算由各认证厂商负责，后端本阶段只落「充值订单」骨架：
- 套餐目录只读展示（不受 provider 开关影响）；
- 发起充值按 provider 分档：disabled→503、mock→待付订单+模拟支付链接、real→501；
- 订单状态查询读取本地订单；支付回调（仅 mock/联调）把订单置为已付并给出额度增量提示。

kind：realname 实名认证（人脸核验）/ marriage 婚姻状况核验。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RechargeKind = Literal["realname", "marriage"]
RechargeStatus = Literal["pending", "paid", "failed", "cancelled"]


class QuotaPackage(BaseModel):
    """充值套餐档（只读目录）。"""

    id: str
    kind: RechargeKind
    name: str
    quantity: int = Field(ge=1, description="本档包含的核验次数")
    price: float = Field(ge=0, description="价格（元）")
    currency: str = "CNY"
    enabled: bool = True


class QuotaPackageList(BaseModel):
    packages: list[QuotaPackage] = Field(default_factory=list)
    provider: str = Field(description="当前生效的充值 provider：disabled/mock/real")
    recharge_enabled: bool = Field(description="是否允许发起充值（provider≠disabled）")


class RechargeCreateRequest(BaseModel):
    kind: RechargeKind
    package_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=999, description="购买份数")


class RechargeOrder(BaseModel):
    order_no: str
    kind: RechargeKind
    package_id: str
    package_name: str
    quantity: int
    unit_price: float
    total_amount: float
    currency: str
    status: RechargeStatus
    provider: str
    pay_url: str | None = None
    qr_code_url: str | None = None
    created_at: datetime
    paid_at: datetime | None = None


class RechargeCallbackRequest(BaseModel):
    """支付回调（仅 mock/联调；real 由厂商签名回调驱动，不走本接口）。"""

    status: Literal["paid", "failed"] = "paid"
