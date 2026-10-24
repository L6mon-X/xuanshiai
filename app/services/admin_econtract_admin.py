"""电子合同（A3）服务：模板 / 印章 / 合同 / 签署流水 / 配置。

合同发起与作废走 ``app/services/esign`` 适配层；未配置时在写库前 503，
不会留下"已发起"却没有真实签署流程的合同行。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sensitive_fields import mask_phone
from app.schemas.admin_econtract_admin import (
    EcontractConfig,
    EcontractConfigUpdate,
    EcontractCreate,
    EcontractDetail,
    EcontractEventItem,
    EcontractItem,
    EcontractPage,
    EcontractSealCreate,
    EcontractSealItem,
    EcontractSealUpdate,
    EcontractTemplateCreate,
    EcontractTemplateItem,
    EcontractTemplatePage,
    EcontractTemplateUpdate,
    EcontractVoidRequest,
)
from app.services import admin_config as config_service
from app.services.esign.providers import get_esign_provider, provider_status

_CONFIG_NAMESPACE = "econtract_config"

_TEMPLATE_SELECT = """SELECT id, name, contract_type, provider_template_id, content, file_url, status,
    usage_count, created_at, updated_at FROM admin_econtract_template"""

_SEAL_SELECT = """SELECT id, name, seal_type, image_url, authorized_person, provider_seal_id, status,
    created_at, updated_at FROM admin_econtract_seal"""

_CONTRACT_SELECT = """SELECT c.id, c.contract_no, c.template_id, t.name AS template_name, c.seal_id,
    s.name AS seal_name, c.title, c.contract_type, c.member_id, c.member_name, c.member_phone,
    c.amount, c.status, c.provider_flow_id, c.sign_url, c.signed_at, c.expire_at,
    c.voided_at, c.void_reason, c.created_at, c.updated_at
    FROM admin_econtract c
    LEFT JOIN admin_econtract_template t ON t.id = c.template_id
    LEFT JOIN admin_econtract_seal s ON s.id = c.seal_id"""


def _contract_item(row: Any) -> EcontractItem:
    data = dict(row)
    data["member_phone"] = mask_phone(data.get("member_phone")) or None
    if data.get("amount") is not None:
        data["amount"] = float(data["amount"])
    return EcontractItem(**data)


# ─────────────────────────── 配置 ───────────────────────────


async def get_config(db: AsyncSession) -> EcontractConfig:
    snapshot = await config_service.get_config(db, _CONFIG_NAMESPACE)
    config = snapshot.config if isinstance(snapshot.config, dict) else {}
    status = provider_status()
    return EcontractConfig(
        secret_id_configured=bool(status["secret_id_configured"]),
        secret_key_configured=bool(status["secret_key_configured"]),
        operator_configured=bool(status["operator_configured"]),
        configured=bool(status["configured"]),
        adapter_implemented=bool(status["adapter_implemented"]),
        enabled=bool(config.get("enabled")),
        items=list(config.get("items") or []),
        version=snapshot.version,
        updated_at=snapshot.updated_at,
    )


async def update_config(
    db: AsyncSession, admin_id: int, body: EcontractConfigUpdate
) -> EcontractConfig:
    changes = body.model_dump(exclude_unset=True)
    await config_service.patch_config(
        db, admin_id, _CONFIG_NAMESPACE, changes, summary=f"更新电子签配置：{'/'.join(changes)}"
    )
    return await get_config(db)


# ─────────────────────────── 模板 ───────────────────────────


async def _get_template(db: AsyncSession, template_id: int) -> EcontractTemplateItem:
    row = (
        await db.execute(text(f"{_TEMPLATE_SELECT} WHERE id = :id"), {"id": template_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="合同模板不存在")
    return EcontractTemplateItem(**dict(row))


async def list_templates(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None,
    contract_type: str | None,
    status: int | None,
) -> EcontractTemplatePage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append("name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if contract_type:
        where.append("contract_type = :contract_type")
        params["contract_type"] = contract_type
    if status in (0, 1):
        where.append("status = :status")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        (
            await db.execute(
                text(f"SELECT COUNT(*) FROM admin_econtract_template {where_sql}"), params
            )
        ).scalar()
        or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_TEMPLATE_SELECT} {where_sql} ORDER BY id DESC LIMIT :limit OFFSET :offset"),
            params,
        )
    ).mappings().all()
    return EcontractTemplatePage(
        items=[EcontractTemplateItem(**dict(r)) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def create_template(
    db: AsyncSession, admin_id: int, body: EcontractTemplateCreate
) -> EcontractTemplateItem:
    result = await db.execute(
        text(
            "INSERT INTO admin_econtract_template"
            " (name, contract_type, provider_template_id, content, file_url, status, created_by)"
            " VALUES (:name, :contract_type, :provider_template_id, :content, :file_url, :status, :actor)"
        ),
        {**body.model_dump(), "actor": admin_id},
    )
    item = await _get_template(db, int(result.lastrowid))
    await _audit(db, admin_id, "econtract_template.create", "admin_econtract_template", item.id)
    await db.commit()
    return item


async def update_template(
    db: AsyncSession, admin_id: int, template_id: int, body: EcontractTemplateUpdate
) -> EcontractTemplateItem:
    await _get_template(db, template_id)
    values = body.model_dump(exclude_unset=True)
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(
                f"UPDATE admin_econtract_template SET {assignments},"
                " updated_at = UTC_TIMESTAMP() WHERE id = :id"
            ),
            {**values, "id": template_id},
        )
    await _audit(db, admin_id, "econtract_template.update", "admin_econtract_template", template_id)
    await db.commit()
    return await _get_template(db, template_id)


async def delete_template(db: AsyncSession, admin_id: int, template_id: int) -> None:
    await _get_template(db, template_id)
    used = (
        await db.execute(
            text("SELECT 1 FROM admin_econtract WHERE template_id = :id LIMIT 1"),
            {"id": template_id},
        )
    ).scalar_one_or_none()
    if used:
        raise HTTPException(409, detail="该模板已被合同引用，不能删除（可改为停用）")
    await db.execute(
        text("DELETE FROM admin_econtract_template WHERE id = :id"), {"id": template_id}
    )
    await _audit(db, admin_id, "econtract_template.delete", "admin_econtract_template", template_id)
    await db.commit()


# ─────────────────────────── 印章 ───────────────────────────


async def _get_seal(db: AsyncSession, seal_id: int) -> EcontractSealItem:
    row = (
        await db.execute(text(f"{_SEAL_SELECT} WHERE id = :id"), {"id": seal_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="电子印章不存在")
    return EcontractSealItem(**dict(row))


async def list_seals(db: AsyncSession, status: int | None) -> list[EcontractSealItem]:
    where_sql = "WHERE status = :status" if status in (0, 1) else ""
    params = {"status": status} if where_sql else {}
    rows = (
        await db.execute(text(f"{_SEAL_SELECT} {where_sql} ORDER BY id DESC"), params)
    ).mappings().all()
    return [EcontractSealItem(**dict(r)) for r in rows]


async def create_seal(
    db: AsyncSession, admin_id: int, body: EcontractSealCreate
) -> EcontractSealItem:
    result = await db.execute(
        text(
            "INSERT INTO admin_econtract_seal"
            " (name, seal_type, image_url, authorized_person, provider_seal_id, created_by)"
            " VALUES (:name, :seal_type, :image_url, :authorized_person, :provider_seal_id, :actor)"
        ),
        {**body.model_dump(), "actor": admin_id},
    )
    item = await _get_seal(db, int(result.lastrowid))
    await _audit(db, admin_id, "econtract_seal.create", "admin_econtract_seal", item.id)
    await db.commit()
    return item


async def update_seal(
    db: AsyncSession, admin_id: int, seal_id: int, body: EcontractSealUpdate
) -> EcontractSealItem:
    await _get_seal(db, seal_id)
    values = body.model_dump(exclude_unset=True)
    if values:
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        await db.execute(
            text(
                f"UPDATE admin_econtract_seal SET {assignments},"
                " updated_at = UTC_TIMESTAMP() WHERE id = :id"
            ),
            {**values, "id": seal_id},
        )
    await _audit(db, admin_id, "econtract_seal.update", "admin_econtract_seal", seal_id)
    await db.commit()
    return await _get_seal(db, seal_id)


async def delete_seal(db: AsyncSession, admin_id: int, seal_id: int) -> None:
    await _get_seal(db, seal_id)
    used = (
        await db.execute(
            text("SELECT 1 FROM admin_econtract WHERE seal_id = :id LIMIT 1"), {"id": seal_id}
        )
    ).scalar_one_or_none()
    if used:
        raise HTTPException(409, detail="该印章已被合同引用，不能删除（可改为停用）")
    await db.execute(text("DELETE FROM admin_econtract_seal WHERE id = :id"), {"id": seal_id})
    await _audit(db, admin_id, "econtract_seal.delete", "admin_econtract_seal", seal_id)
    await db.commit()


# ─────────────────────────── 合同 ───────────────────────────


def _contract_no() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"HT{stamp}{uuid.uuid4().hex[:6].upper()}"


async def _get_contract_row(db: AsyncSession, contract_id: int) -> Any:
    row = (
        await db.execute(text(f"{_CONTRACT_SELECT} WHERE c.id = :id"), {"id": contract_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, detail="合同不存在")
    return row


async def list_contracts(
    db: AsyncSession,
    page: int,
    page_size: int,
    keyword: str | None,
    status: str | None,
    template_id: int | None,
    start_date: str | None,
    end_date: str | None,
) -> EcontractPage:
    where: list[str] = []
    params: dict[str, Any] = {}
    if keyword:
        where.append(
            "(c.contract_no LIKE :keyword OR c.title LIKE :keyword OR c.member_name LIKE :keyword)"
        )
        params["keyword"] = f"%{keyword}%"
    if status in {"draft", "signing", "signed", "voided", "expired"}:
        where.append("c.status = :status")
        params["status"] = status
    if template_id is not None:
        where.append("c.template_id = :template_id")
        params["template_id"] = template_id
    if start_date:
        where.append("c.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        where.append("c.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)")
        params["end_date"] = end_date
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM admin_econtract c"
                    " LEFT JOIN admin_econtract_template t ON t.id = c.template_id"
                    " LEFT JOIN admin_econtract_seal s ON s.id = c.seal_id " + where_sql
                ),
                params,
            )
        ).scalar()
        or 0
    )
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await db.execute(
            text(f"{_CONTRACT_SELECT} {where_sql} ORDER BY c.id DESC LIMIT :limit OFFSET :offset"),
            params,
        )
    ).mappings().all()
    return EcontractPage(
        items=[_contract_item(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        has_more=page * page_size < total,
    )


async def get_contract(db: AsyncSession, contract_id: int) -> EcontractDetail:
    row = await _get_contract_row(db, contract_id)
    content = (
        await db.execute(
            text("SELECT content FROM admin_econtract WHERE id = :id"), {"id": contract_id}
        )
    ).scalar_one_or_none()
    events = (
        await db.execute(
            text(
                "SELECT id, event, actor, detail, created_at FROM admin_econtract_event"
                " WHERE contract_id = :id ORDER BY id"
            ),
            {"id": contract_id},
        )
    ).mappings().all()
    data = dict(row)
    data["content"] = content
    data["events"] = [EcontractEventItem(**dict(e)) for e in events]
    data["member_phone"] = mask_phone(data.get("member_phone")) or None
    if data.get("amount") is not None:
        data["amount"] = float(data["amount"])
    return EcontractDetail(**data)


async def create_contract(
    db: AsyncSession, admin_id: int, body: EcontractCreate
) -> EcontractDetail:
    """发起合同：先调电子签，成功后才落库（避免假流程）。"""
    provider = get_esign_provider()

    template: EcontractTemplateItem | None = None
    if body.template_id is not None:
        template = await _get_template(db, body.template_id)
        if template.status != 1:
            raise HTTPException(409, detail="模板已停用，不能发起合同")
    seal: EcontractSealItem | None = None
    if body.seal_id is not None:
        seal = await _get_seal(db, body.seal_id)
        if seal.status != 1:
            raise HTTPException(409, detail="印章已停用，不能发起合同")

    member_name = body.member_name
    member_phone = body.member_phone
    if body.member_id is not None:
        row = (
            await db.execute(
                text("SELECT nickname, real_name, phone FROM users WHERE id = :id"),
                {"id": body.member_id},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(422, detail="签署会员不存在")
        member_name = member_name or row["real_name"] or row["nickname"]
        member_phone = member_phone or row["phone"]
    if not member_name or not member_phone:
        raise HTTPException(422, detail="签署人姓名与手机号不完整")

    expire_at = datetime.utcnow() + timedelta(days=body.expire_days) if body.expire_days else None
    content = body.content or (template.content if template else "") or ""
    contract_no = _contract_no()
    flow = await provider.create_flow(
        contract_no=contract_no,
        title=body.title,
        content=content,
        member_name=member_name,
        member_phone=member_phone,
        template_id=template.provider_template_id if template else None,
        seal_id=seal.provider_seal_id if seal else None,
        expire_at=expire_at,
    )
    result = await db.execute(
        text(
            "INSERT INTO admin_econtract"
            " (contract_no, template_id, seal_id, title, contract_type, member_id, member_name,"
            "  member_phone, amount, content, status, provider_flow_id, sign_url, expire_at,"
            "  created_by)"
            " VALUES (:contract_no, :template_id, :seal_id, :title, :contract_type, :member_id,"
            "  :member_name, :member_phone, :amount, :content, 'signing', :flow_id, :sign_url,"
            "  :expire_at, :actor)"
        ),
        {
            "contract_no": contract_no,
            "template_id": body.template_id,
            "seal_id": body.seal_id,
            "title": body.title,
            "contract_type": body.contract_type
            or (template.contract_type if template else "红娘服务协议"),
            "member_id": body.member_id,
            "member_name": member_name,
            "member_phone": member_phone,
            "amount": body.amount,
            "content": content,
            "flow_id": flow.provider_flow_id,
            "sign_url": flow.sign_url,
            "expire_at": expire_at,
            "actor": admin_id,
        },
    )
    contract_id = int(result.lastrowid)
    await _write_event(db, contract_id, "created", "admin", f"合同 {contract_no} 已发起")
    await _write_event(db, contract_id, "sent", "admin", "签署链接已生成")
    if template is not None:
        await db.execute(
            text("UPDATE admin_econtract_template SET usage_count = usage_count + 1 WHERE id = :id"),
            {"id": template.id},
        )
    await _audit(db, admin_id, "econtract.create", "admin_econtract", contract_id)
    await db.commit()
    return await get_contract(db, contract_id)


async def void_contract(
    db: AsyncSession, admin_id: int, contract_id: int, body: EcontractVoidRequest
) -> EcontractDetail:
    row = await _get_contract_row(db, contract_id)
    if row["status"] not in {"draft", "signing"}:
        raise HTTPException(409, detail="仅草稿或签署中的合同可以作废")
    flow_id = row["provider_flow_id"]
    if flow_id:
        # 作废外发且不可逆：先调供应商，失败则不落本地状态。
        await get_esign_provider().void_flow(str(flow_id), body.reason)
    await db.execute(
        text(
            "UPDATE admin_econtract SET status = 'voided', voided_at = UTC_TIMESTAMP(),"
            " void_reason = :reason WHERE id = :id"
        ),
        {"reason": body.reason, "id": contract_id},
    )
    await _write_event(db, contract_id, "voided", "admin", body.reason)
    await _audit(db, admin_id, "econtract.void", "admin_econtract", contract_id, body.reason)
    await db.commit()
    return await get_contract(db, contract_id)


async def _write_event(
    db: AsyncSession, contract_id: int, event: str, actor: str, detail: str | None
) -> None:
    await db.execute(
        text(
            "INSERT INTO admin_econtract_event (contract_id, event, actor, detail)"
            " VALUES (:contract_id, :event, :actor, :detail)"
        ),
        {"contract_id": contract_id, "event": event, "actor": actor, "detail": detail},
    )


async def _audit(
    db: AsyncSession,
    actor_id: int,
    action: str,
    resource_type: str,
    resource_id: int | None,
    reason: str | None = None,
) -> None:
    await db.execute(
        text(
            "INSERT INTO business_audit_log"
            " (actor_user_id, action, resource_type, resource_id, reason)"
            " VALUES (:actor, :action, :resource_type, :resource_id, :reason)"
        ),
        {
            "actor": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "reason": reason,
        },
    )
