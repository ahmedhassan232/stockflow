"""Platform administration (the SaaS operator, not a company user).

Deliberately small: list companies and suspend / re-activate them. A platform admin gets
NO access to a company's business data - the database functions used here return only the
company directory, and they re-check `is_platform_admin` inside PostgreSQL, so a bug in
this router cannot widen access.
"""

import logging
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform", tags=["Platform admin"])


class TenantRow(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    currency: str
    created_at: datetime
    member_count: int
    owner_name: str | None
    owner_email: str | None


class PlatformAuditRow(BaseModel):
    id: uuid.UUID
    action: str
    company_name: str
    actor_name: str
    actor_email: str
    created_at: datetime


class StatusChange(BaseModel):
    status: Literal["active", "suspended"]


async def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.user.is_platform_admin:
        raise ForbiddenError("Platform administrator access required")
    return principal


@router.get("/tenants", response_model=SuccessResponse[list[TenantRow]])
async def list_tenants(
    _: Principal = Depends(require_platform_admin), db: AsyncSession = Depends(get_db)
):
    rows = await db.execute(text("SELECT * FROM platform_list_tenants()"))
    return ok([TenantRow.model_validate(dict(r)) for r in rows.mappings()])


@router.patch("/tenants/{tenant_id}", response_model=SuccessResponse[None])
async def set_tenant_status(
    tenant_id: uuid.UUID,
    data: StatusChange,
    principal: Principal = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Suspending blocks every member of the company on their next request (the status
    is checked on each request, not stored in the token). Data is kept."""
    found = (
        await db.execute(
            text("SELECT platform_set_tenant_status(:t, :s)"), {"t": tenant_id, "s": data.status}
        )
    ).scalar()
    if not found:
        raise NotFoundError("Company not found")
    logger.warning(
        "platform_tenant_status_changed tenant_id=%s status=%s by_user=%s",
        tenant_id,
        data.status,
        principal.user_id,
    )
    return ok(None, f"Company is now {data.status}")


@router.get("/audit-log", response_model=SuccessResponse[list[PlatformAuditRow]])
async def platform_audit_log(
    _: Principal = Depends(require_platform_admin), db: AsyncSession = Depends(get_db)
):
    """Who suspended / re-activated which company, newest first. Written by the database
    in the same transaction as the change; the application cannot edit or delete it."""
    rows = await db.execute(text("SELECT * FROM platform_audit_entries(200)"))
    return ok([PlatformAuditRow.model_validate(dict(r)) for r in rows.mappings()])
