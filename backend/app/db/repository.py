"""Tenant-scoped repository base.

Second isolation layer (the first is RLS): every statement is explicitly filtered by the
repository's tenant id, and inserts are stamped with it regardless of what the caller
passed. Either layer alone prevents cross-tenant access; both are always active.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

MAX_PAGE_SIZE = 100


def like_pattern(term: str) -> str:
    """Escapes LIKE wildcards so user input is always matched literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class TenantRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        if not isinstance(tenant_id, uuid.UUID):
            raise TypeError("tenant_id must be a UUID")
        if not hasattr(self.model, "tenant_id"):
            raise TypeError(f"{self.model.__name__} is not a tenant-owned model")
        self.session = session
        self.tenant_id = tenant_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(self._scoped().where(self.model.id == entity_id))
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ModelT]:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        stmt = self._scoped().order_by(self.model.created_at, self.model.id)
        result = await self.session.execute(stmt.limit(limit).offset(max(0, offset)))
        return result.scalars().all()

    async def search(
        self,
        *,
        q: str | None = None,
        fields: Sequence[Any] = (),
        where: Sequence[ColumnElement[bool]] = (),
        order_by: Sequence[Any] = (),
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[ModelT], int]:
        """Tenant-scoped, server-side filtered + paginated listing."""
        stmt = self._scoped().where(*where)
        if q and fields:
            stmt = stmt.where(or_(*(f.ilike(like_pattern(q)) for f in fields)))
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        order = order_by or (self.model.created_at.desc(), self.model.id)
        rows = await self.session.execute(
            stmt.order_by(*order).limit(max(1, min(limit, MAX_PAGE_SIZE))).offset(max(0, offset))
        )
        return rows.scalars().all(), total

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self._scoped().subquery())
        return (await self.session.execute(stmt)).scalar_one()

    async def add(self, entity: ModelT) -> ModelT:
        entity.tenant_id = self.tenant_id  # never trust a caller-provided tenant id
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity_id: uuid.UUID, values: dict[str, Any]) -> bool:
        if "tenant_id" in values or "id" in values:
            raise ValueError("tenant_id and id are immutable")
        stmt = (
            update(self.model)
            .where(self.model.tenant_id == self.tenant_id, self.model.id == entity_id)
            .values(**values)
        )
        return (await self.session.execute(stmt)).rowcount == 1

    async def delete(self, entity_id: uuid.UUID) -> bool:
        stmt = delete(self.model).where(
            self.model.tenant_id == self.tenant_id, self.model.id == entity_id
        )
        return (await self.session.execute(stmt)).rowcount == 1
