"""Resolves what a user may do inside one company. Called on EVERY tenant request, so a
revoked membership, suspended company or changed role takes effect immediately – nothing
about authorization is trusted from the access token except "which company was selected"."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.modules.authorization.defaults import OWNER_ROLE_CODE
from app.modules.authorization.models import Membership, MembershipBranch, Role, RolePermission
from app.modules.authorization.permissions import ALL_PERMISSIONS
from app.modules.tenants.models import Tenant


@dataclass(frozen=True, slots=True)
class TenantAccess:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
    role_id: uuid.UUID
    role_code: str
    role_name: str
    permissions: frozenset[str]
    restricted_to_branches: bool
    branch_ids: frozenset[uuid.UUID]
    tenant: Tenant

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def can_access_branch(self, branch_id: uuid.UUID | None) -> bool:
        if not self.restricted_to_branches:
            return True
        return branch_id is not None and branch_id in self.branch_ids


async def load_tenant_access(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> TenantAccess:
    """Requires the transaction context to be (tenant_id, user_id)."""
    row = (
        await session.execute(
            select(Membership, Role, Tenant)
            .join(Role, (Role.tenant_id == Membership.tenant_id) & (Role.id == Membership.role_id))
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None:
        raise ForbiddenError("You are not a member of this company", code="NOT_A_MEMBER")
    membership, role, tenant = row
    if membership.status != "active":
        raise ForbiddenError(
            "Your access to this company is not active", code="MEMBERSHIP_INACTIVE"
        )
    if tenant.status != "active":
        raise ForbiddenError("This company is suspended", code="TENANT_SUSPENDED")

    if role.is_system and role.code == OWNER_ROLE_CODE:
        permissions = ALL_PERMISSIONS
    else:
        codes = await session.execute(
            select(RolePermission.permission_code).where(
                RolePermission.tenant_id == tenant_id, RolePermission.role_id == role.id
            )
        )
        permissions = frozenset(codes.scalars().all())

    branch_ids: frozenset[uuid.UUID] = frozenset()
    if membership.restricted_to_branches:
        ids = await session.execute(
            select(MembershipBranch.branch_id).where(
                MembershipBranch.tenant_id == tenant_id,
                MembershipBranch.membership_id == membership.id,
            )
        )
        branch_ids = frozenset(ids.scalars().all())

    return TenantAccess(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership.id,
        role_id=role.id,
        role_code=role.code,
        role_name=role.name,
        permissions=permissions,
        restricted_to_branches=membership.restricted_to_branches,
        branch_ids=branch_ids,
        tenant=tenant,
    )
