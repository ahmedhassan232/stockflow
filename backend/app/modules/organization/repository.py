import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.db.repository import TenantRepository
from app.modules.organization.models import Branch, Warehouse


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class BranchRepository(TenantRepository[Branch]):
    model = Branch

    async def search(
        self,
        *,
        q: str | None,
        is_active: bool | None,
        only_ids: frozenset[uuid.UUID] | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Branch], int]:
        stmt = self._scoped()
        if q:
            stmt = stmt.where(or_(Branch.name.ilike(_like(q)), Branch.code.ilike(_like(q))))
        if is_active is not None:
            stmt = stmt.where(Branch.is_active.is_(is_active))
        if only_ids is not None:
            stmt = stmt.where(Branch.id.in_(only_ids))
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Branch.name, Branch.id).limit(limit).offset(offset)
        )
        return rows.scalars().all(), total


class WarehouseRepository(TenantRepository[Warehouse]):
    model = Warehouse

    async def search(
        self,
        *,
        q: str | None,
        is_active: bool | None,
        branch_id: uuid.UUID | None,
        only_branch_ids: frozenset[uuid.UUID] | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Warehouse], int]:
        stmt = self._scoped()
        if q:
            stmt = stmt.where(or_(Warehouse.name.ilike(_like(q)), Warehouse.code.ilike(_like(q))))
        if is_active is not None:
            stmt = stmt.where(Warehouse.is_active.is_(is_active))
        if branch_id is not None:
            stmt = stmt.where(Warehouse.branch_id == branch_id)
        if only_branch_ids is not None:
            stmt = stmt.where(Warehouse.branch_id.in_(only_branch_ids))
        total = (
            await self.session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(Warehouse.name, Warehouse.id).limit(limit).offset(offset)
        )
        return rows.scalars().all(), total
