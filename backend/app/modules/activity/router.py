import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.activity.models import AuditLog, Notification
from app.modules.auth.dependencies import get_tenant_access, require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.users.models import User

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])
audit_router = APIRouter(prefix="/audit-logs", tags=["Audit log"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    data: dict[str, Any] | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(Page[NotificationOut]):
    unread: int


class AuditLogOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str | None
    data: dict[str, Any] | None
    user_name: str | None
    created_at: datetime


def _visible(access: TenantAccess):
    return [
        Notification.tenant_id == access.tenant_id,
        or_(
            Notification.required_permission.is_(None),
            Notification.required_permission.in_(access.permissions),
        ),
    ]


@notifications_router.get("", response_model=SuccessResponse[NotificationList])
async def list_notifications(
    page: PageParams = Depends(),
    unread_only: bool = False,
    access: TenantAccess = Depends(get_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    where = _visible(access)
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(*where, Notification.read_at.is_(None))
        )
    ).scalar_one()
    if unread_only:
        where.append(Notification.read_at.is_(None))
    total = (
        await db.execute(select(func.count()).select_from(Notification).where(*where))
    ).scalar_one()
    rows = await db.execute(
        select(Notification)
        .where(*where)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(page.page_size)
        .offset(page.offset)
    )
    return ok(
        NotificationList(
            items=[NotificationOut.model_validate(n) for n in rows.scalars().all()],
            total=total,
            page=page.page,
            page_size=page.page_size,
            unread=unread,
        )
    )


@notifications_router.post("/read-all", response_model=SuccessResponse[None])
async def read_all(
    access: TenantAccess = Depends(get_tenant_access), db: AsyncSession = Depends(get_db)
):
    await db.execute(
        update(Notification)
        .where(*_visible(access), Notification.read_at.is_(None))
        .values(read_at=func.now(), dedupe_key=None)
    )
    return ok(None, "Notifications marked as read")


@notifications_router.post("/{notification_id}/read", response_model=SuccessResponse[None])
async def read_one(
    notification_id: uuid.UUID,
    access: TenantAccess = Depends(get_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(
            *_visible(access), Notification.id == notification_id, Notification.read_at.is_(None)
        )
        .values(read_at=func.now(), dedupe_key=None)
    )
    return ok(None, "Notification marked as read")


@audit_router.get("", response_model=SuccessResponse[Page[AuditLogOut]])
async def list_audit_logs(
    page: PageParams = Depends(),
    entity_type: str | None = None,
    access: TenantAccess = Depends(require_permission("settings.view")),
    db: AsyncSession = Depends(get_db),
):
    where = [AuditLog.tenant_id == access.tenant_id]
    if entity_type:
        where.append(AuditLog.entity_type == entity_type)
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*where))
    ).scalar_one()
    rows = await db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*where)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(page.page_size)
        .offset(page.offset)
    )
    items = [
        AuditLogOut(
            id=a.id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            summary=a.summary,
            data=a.data,
            user_name=name,
            created_at=a.created_at,
        )
        for a, name in rows.all()
    ]
    return ok(Page(items=items, total=total, page=page.page, page_size=page.page_size))
