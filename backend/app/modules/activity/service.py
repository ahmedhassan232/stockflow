import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activity.models import AuditLog, Notification
from app.modules.authorization.service import TenantAccess
from app.modules.catalog.models import Product
from app.modules.inventory.models import StockBalance


def audit(
    db: AsyncSession,
    access: TenantAccess,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Written in the caller's transaction: the log row exists iff the change committed."""
    db.add(
        AuditLog(
            tenant_id=access.tenant_id,
            user_id=access.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            data=data,
        )
    )


async def notify_if_low_stock(db: AsyncSession, balance: StockBalance, product: Product) -> None:
    """One open notification per (warehouse, product) until somebody reads it."""
    if balance.minimum_stock_level <= 0 or balance.quantity > balance.minimum_stock_level:
        return
    await db.execute(
        pg_insert(Notification)
        .values(
            tenant_id=balance.tenant_id,
            type="low_stock",
            title=product.name,
            body=f"{balance.quantity} / {balance.minimum_stock_level}",
            data={
                "product_id": str(product.id),
                "warehouse_id": str(balance.warehouse_id),
                "sku": product.sku,
                "quantity": str(balance.quantity),
                "minimum_stock_level": str(balance.minimum_stock_level),
            },
            required_permission="inventory.view",
            dedupe_key=f"low_stock:{balance.warehouse_id}:{product.id}",
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "dedupe_key"])
    )
