import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantRepository
from app.modules.authorization.models import Membership, Role


class RoleRepository(TenantRepository[Role]):
    model = Role

    async def get_by_code(self, code: str) -> Role | None:
        result = await self.session.execute(self._scoped().where(Role.code == code))
        return result.scalar_one_or_none()


class MembershipRepository(TenantRepository[Membership]):
    model = Membership

    async def get_for_user(self, user_id: uuid.UUID) -> Membership | None:
        result = await self.session.execute(self._scoped().where(Membership.user_id == user_id))
        return result.scalar_one_or_none()


async def list_memberships_of_user(
    session: AsyncSession, user_id: uuid.UUID
) -> Sequence[Membership]:
    """Cross-tenant by design: the caller's OWN memberships (company chooser).
    Requires `app.user_id` to be set to the same user; RLS returns nothing otherwise."""
    result = await session.execute(
        select(Membership).where(Membership.user_id == user_id).order_by(Membership.joined_at)
    )
    return result.scalars().all()
