"""Authentication / authorization dependencies used by every protected router."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthenticatedError
from app.db.session import get_db
from app.db.tenant import TenantContext, apply_context
from app.modules.auth.models import AuthSession
from app.modules.auth.security import decode_access_token
from app.modules.authorization.service import TenantAccess, load_tenant_access
from app.modules.users.models import User

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")
_TOUCH_EVERY = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated person on a live session (no company implied)."""

    user: User
    session_id: uuid.UUID
    tenant_id: uuid.UUID | None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise UnauthenticatedError()
    claims = decode_access_token(credentials.credentials)

    if not db.in_transaction():
        await db.begin()
    # The ONLY place a request's tenant context is set: from the signed token, and it is
    # re-validated against the membership table before any tenant data is touched.
    await apply_context(db, TenantContext(tenant_id=claims.tenant_id, user_id=claims.user_id))

    row = (
        await db.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(AuthSession.id == claims.session_id, AuthSession.user_id == claims.user_id)
        )
    ).first()
    now = datetime.now(UTC)
    if row is None:
        raise UnauthenticatedError("Session not found")
    session, user = row
    if session.revoked_at is not None or session.expires_at <= now:
        raise UnauthenticatedError("Session has been revoked", code="SESSION_REVOKED")
    if not user.is_active:
        raise UnauthenticatedError("Account is disabled", code="ACCOUNT_DISABLED")
    if now - session.last_seen_at > _TOUCH_EVERY:
        session.last_seen_at = now
    return Principal(user=user, session_id=session.id, tenant_id=claims.tenant_id)


async def get_tenant_access(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> TenantAccess:
    if principal.tenant_id is None:
        raise ForbiddenError("Select a company first", code="NO_ACTIVE_COMPANY")
    return await load_tenant_access(db, user_id=principal.user_id, tenant_id=principal.tenant_id)


def require_permission(*permissions: str) -> Callable[..., Awaitable[TenantAccess]]:
    """Dependency factory: the caller must hold ALL listed permissions in the active company."""

    async def dependency(access: TenantAccess = Depends(get_tenant_access)) -> TenantAccess:
        missing = [p for p in permissions if not access.has(p)]
        if missing:
            raise ForbiddenError(details={"missing_permissions": missing})
        return access

    return dependency


async def verify_origin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """CSRF defence for the cookie-authenticated endpoints (refresh / logout): a browser
    always sends Origin on cross-site POSTs, and it must be this site or an allowlisted one."""
    origin = request.headers.get("origin")
    if origin is None:
        return  # non-browser client: no ambient cookie to abuse
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    if urlsplit(origin).netloc == host or origin.rstrip("/") in settings.cors_origin_list:
        return
    raise ForbiddenError("Cross-site request rejected", code="CSRF_REJECTED")
