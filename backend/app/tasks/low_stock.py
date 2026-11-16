"""Scheduled low-stock scan.

Sales raise a low-stock notification inside their own transaction. Stock can also fall
through adjustments, transfers and purchase returns, or a minimum level can be raised
above the current balance - this periodic scan catches those cases.

Isolation: the job asks the database only for the ids of active companies, then handles
each company in its OWN transaction with that company's tenant context, so every query
runs under the same RLS policies as a normal request. One company failing does not stop
the others.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.tenant import TenantContext, apply_context
from app.modules.activity.service import notify_if_low_stock
from app.modules.catalog.models import Product
from app.modules.inventory.models import StockBalance

log = logging.getLogger(__name__)


async def _scan_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    rows = await session.execute(
        select(StockBalance, Product)
        .join(
            Product,
            (Product.tenant_id == StockBalance.tenant_id) & (Product.id == StockBalance.product_id),
        )
        .where(
            StockBalance.tenant_id == tenant_id,
            StockBalance.minimum_stock_level > 0,
            StockBalance.quantity <= StockBalance.minimum_stock_level,
            Product.is_active.is_(True),
            Product.track_inventory.is_(True),
        )
    )
    found = 0
    for balance, product in rows.all():
        await notify_if_low_stock(session, balance, product)
        found += 1
    return found


async def scan_low_stock(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with sessionmaker() as session, session.begin():
        tenant_ids = (await session.execute(text("SELECT app_active_tenant_ids()"))).scalars().all()
    result = {"companies": 0, "low_items": 0, "failed": 0}
    for tenant_id in tenant_ids:
        try:
            async with sessionmaker() as session, session.begin():
                await apply_context(session, TenantContext(tenant_id=tenant_id))
                result["low_items"] += await _scan_tenant(session, tenant_id)
            result["companies"] += 1
        except Exception:
            result["failed"] += 1
            log.exception("low_stock_scan_failed tenant_id=%s", tenant_id)
    log.info("low_stock_scan_done %s", result)
    return result


def run_scan() -> dict[str, int]:
    """Entry point for the Celery worker (sync). Uses its own short-lived engine because
    each task run has its own event loop."""

    async def _run() -> dict[str, int]:
        engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        try:
            return await scan_low_stock(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# ───────────────────────── daily e-mail digest ─────────────────────────


async def _digest_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[str, list[str]] | None:
    """Returns (e-mail body, recipients) or None when nothing is low / nobody to tell."""
    from app.modules.authorization.models import Membership, Role, RolePermission
    from app.modules.organization.models import Warehouse
    from app.modules.tenants.models import Tenant
    from app.modules.users.models import User

    low = (
        await session.execute(
            select(
                Product.name,
                Product.sku,
                Warehouse.name,
                StockBalance.quantity,
                StockBalance.minimum_stock_level,
            )
            .join(
                Product,
                (Product.tenant_id == StockBalance.tenant_id)
                & (Product.id == StockBalance.product_id),
            )
            .join(
                Warehouse,
                (Warehouse.tenant_id == StockBalance.tenant_id)
                & (Warehouse.id == StockBalance.warehouse_id),
            )
            .where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.minimum_stock_level > 0,
                StockBalance.quantity <= StockBalance.minimum_stock_level,
                Product.is_active.is_(True),
                Product.track_inventory.is_(True),
            )
            .order_by(Product.name)
            .limit(200)
        )
    ).all()
    if not low:
        return None
    # Only people who may see stock: owners, and roles holding inventory.view.
    can_view = (
        select(RolePermission.role_id)
        .where(
            RolePermission.tenant_id == tenant_id,
            RolePermission.permission_code == "inventory.view",
        )
        .scalar_subquery()
    )
    recipients = (
        (
            await session.execute(
                select(User.email)
                .join(Membership, Membership.user_id == User.id)
                .join(
                    Role, (Role.tenant_id == Membership.tenant_id) & (Role.id == Membership.role_id)
                )
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.status == "active",
                    User.is_active.is_(True),
                    User.email_verified.is_(True),
                    (Role.code == "owner") | Role.id.in_(can_view),
                )
            )
        )
        .scalars()
        .all()
    )
    if not recipients:
        return None
    company = (
        await session.execute(select(Tenant.name).where(Tenant.id == tenant_id))
    ).scalar() or ""
    lines = [
        f"- {name} ({sku}) @ {warehouse}: {quantity} / {minimum}"
        for name, sku, warehouse, quantity, minimum in low
    ]
    body = (
        f"{company}\n\nأصناف وصلت إلى الحد الأدنى أو أقل (الرصيد / الحد الأدنى):\n"
        "Items at or below their minimum level (on hand / minimum):\n\n" + "\n".join(lines)
    )
    return body, list(recipients)


async def send_low_stock_digests(
    sessionmaker: async_sessionmaker[AsyncSession], redis_client
) -> dict[str, int]:
    """At most one digest per company per UTC day (guarded in Redis), sent only to
    verified addresses. Each company is read inside its own tenant context."""
    from datetime import UTC, datetime

    from app.core.email import Email, deliver

    async with sessionmaker() as session, session.begin():
        tenant_ids = (await session.execute(text("SELECT app_active_tenant_ids()"))).scalars().all()
    day = datetime.now(UTC).date().isoformat()
    result = {"companies": 0, "emails": 0, "failed": 0}
    for tenant_id in tenant_ids:
        try:
            async with sessionmaker() as session, session.begin():
                await apply_context(session, TenantContext(tenant_id=tenant_id))
                digest = await _digest_for_tenant(session, tenant_id)
            if digest is None:
                continue
            if not redis_client.set(f"stockflow:digest:{tenant_id}:{day}", "1", nx=True, ex=172800):
                continue  # already sent today
            body, recipients = digest
            for to in recipients:
                deliver(
                    Email(
                        to=to,
                        subject="StockFlow – تنبيه المخزون المنخفض / Low stock digest",
                        body=body,
                    )
                )
                result["emails"] += 1
            result["companies"] += 1
        except Exception:
            result["failed"] += 1
            log.exception("low_stock_digest_failed tenant_id=%s", tenant_id)
    log.info("low_stock_digest_done %s", result)
    return result


def run_digest() -> dict[str, int]:
    import redis

    async def _run() -> dict[str, int]:
        engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        client = redis.Redis.from_url(get_settings().redis_url)
        try:
            return await send_low_stock_digests(
                async_sessionmaker(engine, expire_on_commit=False), client
            )
        finally:
            client.close()
            await engine.dispose()

    return asyncio.run(_run())
