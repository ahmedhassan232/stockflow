import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.db.tenant import TenantContext, apply_context
from app.modules.authorization.defaults import DEFAULT_ROLES, OWNER_ROLE_CODE
from app.modules.authorization.models import Membership, Role, RolePermission
from app.modules.authorization.permissions import DEFAULT_ROLE_PERMISSIONS
from app.modules.authorization.repository import MembershipRepository, RoleRepository
from app.modules.organization.models import Branch, Warehouse
from app.modules.organization.repository import BranchRepository, WarehouseRepository
from app.modules.settings.models import CompanySettings
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import ProvisionedTenant, TenantCreate
from app.modules.users.models import User

DEFAULT_CODE = "MAIN"


class TenantProvisioningService:
    """Creates a company and everything it needs to be usable.

    Runs entirely inside the caller's transaction (it never commits), so a failure at
    any step leaves no partial company behind.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def provision(self, *, owner_user_id: uuid.UUID, data: TenantCreate) -> ProvisionedTenant:
        try:
            ZoneInfo(data.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise AppError("Unknown timezone") from exc

        owner = await self.session.get(User, owner_user_id)
        if owner is None or not owner.is_active:
            raise NotFoundError("Owner user not found")

        # The new tenant id is generated server-side and becomes the transaction's
        # context; RLS then only accepts rows stamped with exactly this id.
        tenant_id = uuid.uuid4()
        await apply_context(self.session, TenantContext(tenant_id=tenant_id, user_id=owner_user_id))

        tenant = Tenant(
            id=tenant_id,
            name=data.name,
            slug=data.slug,
            email=data.email,
            phone=data.phone,
            currency=data.currency,
            timezone=data.timezone,
        )
        try:
            # Savepoint: a duplicate slug must not poison the caller's transaction.
            # (Other companies' slugs are invisible under RLS, so the unique
            # constraint – not a SELECT – is the source of truth.)
            async with self.session.begin_nested():
                self.session.add(tenant)
                await self.session.flush()
        except IntegrityError as exc:
            raise ConflictError("This company identifier is already taken") from exc

        self.session.add(CompanySettings(tenant_id=tenant_id))

        roles = RoleRepository(self.session, tenant_id)
        owner_role: Role | None = None
        for code, name, _name_ar in DEFAULT_ROLES:
            role = await roles.add(Role(code=code, name=name, is_system=True))
            if code == OWNER_ROLE_CODE:
                owner_role = role  # implicit: all permissions
            self.session.add_all(
                RolePermission(tenant_id=tenant_id, role_id=role.id, permission_code=permission)
                for permission in sorted(DEFAULT_ROLE_PERMISSIONS.get(code, ()))
            )
        await self.session.flush()
        if owner_role is None:
            raise RuntimeError("Default roles must include the owner role")

        membership = await MembershipRepository(self.session, tenant_id).add(
            Membership(user_id=owner_user_id, role_id=owner_role.id, status="active")
        )

        branch_id = warehouse_id = None
        if data.create_default_branch:
            branch = await BranchRepository(self.session, tenant_id).add(
                Branch(
                    name=data.default_branch_name,
                    code=DEFAULT_CODE,
                    manager_membership_id=membership.id,
                )
            )
            warehouse = await WarehouseRepository(self.session, tenant_id).add(
                Warehouse(name=data.default_warehouse_name, code=DEFAULT_CODE, branch_id=branch.id)
            )
            branch_id, warehouse_id = branch.id, warehouse.id

        return ProvisionedTenant(
            tenant_id=tenant_id,
            owner_membership_id=membership.id,
            owner_role_id=owner_role.id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
        )
