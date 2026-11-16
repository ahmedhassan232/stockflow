"""Tenant context: the single place where `app.tenant_id` / `app.user_id` are set.

The values are applied with `set_config(name, value, is_local => true)`, so they live
only until the current transaction ends. Consequences:

* a pooled connection can never carry one request's tenant into another request;
* if code commits mid-request, the context is gone and RLS hides everything
  (fail closed) until it is applied again.

The ids passed here must come from a VALIDATED membership (Phase 3 derives them from the
access token + membership lookup) – never from a tenant id supplied by the client.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker

_SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant_id, true),"
    "       set_config('app.user_id', :user_id, true)"
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Identity a unit of work runs under."""

    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


async def apply_context(session: AsyncSession, ctx: TenantContext) -> None:
    """Bind the context to the session's CURRENT transaction."""
    if not session.in_transaction():
        raise RuntimeError("apply_context() must be called inside a transaction")
    # str(uuid.UUID) guarantees the value is a canonical UUID, never arbitrary text.
    await session.execute(
        _SET_CONTEXT,
        {
            "tenant_id": str(ctx.tenant_id) if ctx.tenant_id else "",
            "user_id": str(ctx.user_id) if ctx.user_id else "",
        },
    )


@asynccontextmanager
async def context_transaction(ctx: TenantContext) -> AsyncIterator[AsyncSession]:
    """One session, one transaction, one context. Commits on success, rolls back on error."""
    async with get_sessionmaker()() as session:
        async with session.begin():
            await apply_context(session, ctx)
            yield session
