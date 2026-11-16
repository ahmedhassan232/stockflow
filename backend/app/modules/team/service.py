"""Employees, roles and company settings.

Privilege-escalation rules (enforced here, tested in tests/test_team.py):
* nobody can change their own membership;
* only an owner can grant, change or suspend an owner;
* you can only assign a role whose permissions are a subset of your own;
* the owner role itself cannot be edited or deleted.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.email import Email, deliver
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.activity.service import audit
from app.modules.auth import security
from app.modules.auth.models import PasswordResetToken
from app.modules.authorization.defaults import OWNER_ROLE_CODE
from app.modules.authorization.models import Membership, MembershipBranch, Role, RolePermission
from app.modules.authorization.permissions import ALL_PERMISSIONS, PERMISSIONS
from app.modules.authorization.service import TenantAccess
from app.modules.organization.models import Branch
from app.modules.settings.service import get_company_settings
from app.modules.team.schemas import (
    EmployeeInvite,
    EmployeeOut,
    EmployeeUpdate,
    PermissionOut,
    RoleIn,
    RoleOut,
    SettingsOut,
    SettingsUpdate,
)
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

INVITE_TTL_HOURS = 72


def _is_owner(role: Role) -> bool:
    return role.is_system and role.code == OWNER_ROLE_CODE


class TeamService:
    def __init__(self, db: AsyncSession, access: TenantAccess, settings: Settings) -> None:
        self.db = db
        self.access = access
        self.tenant_id = access.tenant_id
        self.settings = settings

    # ── roles ──

    async def _role(self, role_id: uuid.UUID) -> Role:
        role = (
            await self.db.execute(
                select(Role).where(Role.tenant_id == self.tenant_id, Role.id == role_id)
            )
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("Role not found")
        return role

    async def _role_permissions(self, role: Role) -> frozenset[str]:
        if _is_owner(role):
            return ALL_PERMISSIONS
        rows = await self.db.execute(
            select(RolePermission.permission_code).where(
                RolePermission.tenant_id == self.tenant_id, RolePermission.role_id == role.id
            )
        )
        return frozenset(rows.scalars().all())

    async def _assignable(self, role: Role) -> None:
        if _is_owner(role) and self.access.role_code != OWNER_ROLE_CODE:
            raise ForbiddenError("Only an owner can assign the owner role", code="OWNER_ONLY")
        extra = await self._role_permissions(role) - self.access.permissions
        if extra:
            raise ForbiddenError(
                "You cannot assign a role that has more permissions than you have",
                code="PRIVILEGE_ESCALATION",
            )

    async def list_roles(self) -> list[RoleOut]:
        roles = (
            (
                await self.db.execute(
                    select(Role)
                    .where(Role.tenant_id == self.tenant_id)
                    .order_by(Role.created_at, Role.code)
                )
            )
            .scalars()
            .all()
        )
        counts = dict(
            (
                await self.db.execute(
                    select(Membership.role_id, func.count())
                    .where(Membership.tenant_id == self.tenant_id, Membership.status != "revoked")
                    .group_by(Membership.role_id)
                )
            ).all()
        )
        return [
            RoleOut(
                id=r.id,
                code=r.code,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
                is_owner=_is_owner(r),
                permissions=sorted(await self._role_permissions(r)),
                member_count=counts.get(r.id, 0),
            )
            for r in roles
        ]

    async def _role_out(self, role: Role) -> RoleOut:
        return next(r for r in await self.list_roles() if r.id == role.id)

    def _validated(self, permissions: list[str]) -> set[str]:
        unknown = set(permissions) - ALL_PERMISSIONS
        if unknown:
            raise AppError(
                "Unknown permission", code="INVALID_PERMISSION", details={"codes": sorted(unknown)}
            )
        return set(permissions)

    async def _set_permissions(self, role: Role, permissions: set[str]) -> None:
        await self.db.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == self.tenant_id, RolePermission.role_id == role.id
            )
        )
        for code in sorted(permissions):
            self.db.add(
                RolePermission(tenant_id=self.tenant_id, role_id=role.id, permission_code=code)
            )
        await self.db.flush()

    async def create_role(self, data: RoleIn) -> RoleOut:
        permissions = self._validated(data.permissions)
        slug = re.sub(r"[^a-z0-9]+", "_", data.name.lower()).strip("_")
        code = f"custom_{slug}"[:40] if slug and slug[0].isalpha() else "custom"
        role = Role(
            tenant_id=self.tenant_id,
            code=f"{code}_{uuid.uuid4().hex[:6]}",
            name=data.name,
            description=data.description,
            is_system=False,
        )
        self.db.add(role)
        await self.db.flush()
        await self._set_permissions(role, permissions)
        audit(self.db, self.access, "role.created", "role", role.id, role.name)
        return await self._role_out(role)

    async def update_role(self, role_id: uuid.UUID, data: RoleIn) -> RoleOut:
        role = await self._role(role_id)
        if _is_owner(role):
            raise ConflictError("The owner role cannot be changed", code="OWNER_ROLE_IMMUTABLE")
        permissions = self._validated(data.permissions)
        before = await self._role_permissions(role)
        role.name, role.description = data.name, data.description
        await self._set_permissions(role, permissions)
        audit(
            self.db,
            self.access,
            "role.updated",
            "role",
            role.id,
            role.name,
            {"added": sorted(permissions - before), "removed": sorted(before - permissions)},
        )
        return await self._role_out(role)

    async def delete_role(self, role_id: uuid.UUID) -> None:
        role = await self._role(role_id)
        if role.is_system:
            raise ConflictError("Built-in roles cannot be deleted", code="SYSTEM_ROLE")
        try:
            async with self.db.begin_nested():
                await self.db.delete(role)
                await self.db.flush()
        except IntegrityError:
            raise ConflictError(
                "This role is still assigned to employees", code="ROLE_IN_USE"
            ) from None
        audit(self.db, self.access, "role.deleted", "role", role_id, role.name)

    @staticmethod
    def permission_catalogue() -> list[PermissionOut]:
        return [
            PermissionOut(code=code, description=text, group=code.split(".")[0])
            for code, text in PERMISSIONS.items()
        ]

    # ── employees ──

    async def _branches(self, branch_ids: list[uuid.UUID]) -> None:
        if not branch_ids:
            return
        found = await self.db.execute(
            select(func.count())
            .select_from(Branch)
            .where(Branch.tenant_id == self.tenant_id, Branch.id.in_(set(branch_ids)))
        )
        if found.scalar_one() != len(set(branch_ids)):
            raise AppError("Branch not found", code="INVALID_REFERENCE")

    async def _set_branches(self, membership: Membership, branch_ids: list[uuid.UUID]) -> None:
        await self.db.execute(
            delete(MembershipBranch).where(
                MembershipBranch.tenant_id == self.tenant_id,
                MembershipBranch.membership_id == membership.id,
            )
        )
        for branch_id in set(branch_ids):
            self.db.add(
                MembershipBranch(
                    tenant_id=self.tenant_id, membership_id=membership.id, branch_id=branch_id
                )
            )
        await self.db.flush()

    async def list_employees(self, membership_id: uuid.UUID | None = None) -> list[EmployeeOut]:
        where = [Membership.tenant_id == self.tenant_id, Membership.status != "revoked"]
        if membership_id:
            where.append(Membership.id == membership_id)
        rows = (
            await self.db.execute(
                select(Membership, User, Role)
                .join(User, User.id == Membership.user_id)
                .join(
                    Role, (Role.tenant_id == Membership.tenant_id) & (Role.id == Membership.role_id)
                )
                .where(*where)
                .order_by(Membership.joined_at, Membership.id)
            )
        ).all()
        branches: dict[uuid.UUID, list[uuid.UUID]] = {}
        for mid, bid in (
            await self.db.execute(
                select(MembershipBranch.membership_id, MembershipBranch.branch_id).where(
                    MembershipBranch.tenant_id == self.tenant_id
                )
            )
        ).all():
            branches.setdefault(mid, []).append(bid)
        return [
            EmployeeOut(
                id=m.id,
                user_id=u.id,
                full_name=u.full_name,
                email=u.email,
                role_id=r.id,
                role_code=r.code,
                role_name=r.name,
                status=m.status,
                has_password=u.password_hash is not None,
                restricted_to_branches=m.restricted_to_branches,
                branch_ids=branches.get(m.id, []),
                joined_at=m.joined_at,
                is_self=u.id == self.access.user_id,
            )
            for m, u, r in rows
        ]

    async def invite(self, data: EmployeeInvite) -> EmployeeOut:
        role = await self._role(data.role_id)
        await self._assignable(role)
        await self._branches(data.branch_ids or [])
        email = data.email.lower()
        user = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        is_new = user is None
        if user is None:
            # No password yet: the account cannot sign in until the invite link is used.
            user = User(full_name=data.full_name, email=email)
            self.db.add(user)
            await self.db.flush()
        existing = (
            await self.db.execute(
                select(Membership).where(
                    Membership.tenant_id == self.tenant_id, Membership.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status != "revoked":
            raise ConflictError("This person is already an employee", code="ALREADY_MEMBER")
        if existing is None:
            membership = Membership(tenant_id=self.tenant_id, user_id=user.id, role_id=role.id)
            self.db.add(membership)
        else:
            membership = existing
            membership.role_id, membership.status = role.id, "active"
        membership.restricted_to_branches = data.branch_ids is not None
        await self.db.flush()
        await self._set_branches(membership, data.branch_ids or [])

        company = self.access.tenant.name
        base = self.settings.frontend_url.rstrip("/")
        if is_new or user.password_hash is None:
            raw, digest = security.new_opaque_token()
            self.db.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=digest,
                    expires_at=datetime.now(UTC) + timedelta(hours=INVITE_TTL_HOURS),
                )
            )
            link = f"{base}/reset-password?token={raw}"
            body = (
                f"مرحبًا {user.full_name}،\n\nتمت دعوتك للانضمام إلى «{company}» على StockFlow "
                f"بدور «{role.name}». اختر كلمة المرور من الرابط التالي "
                f"(صالح {INVITE_TTL_HOURS} ساعة):\n"
                f"{link}\n\nYou were invited to join “{company}” on StockFlow. "
                f"Set your password using the link above (valid for {INVITE_TTL_HOURS} hours)."
            )
        else:
            body = (
                f"مرحبًا {user.full_name}،\n\nتمت إضافتك إلى «{company}» على StockFlow بدور "
                f"«{role.name}». سجّل الدخول بحسابك الحالي: {base}/login\n\n"
                f"You were added to “{company}” on StockFlow. Sign in with your existing account."
            )
        await self.db.flush()
        deliver(Email(to=user.email, subject=f"StockFlow – دعوة للانضمام إلى {company}", body=body))
        audit(
            self.db,
            self.access,
            "employee.invited",
            "membership",
            membership.id,
            email,
            {"role": role.code},
        )
        return (await self.list_employees(membership.id))[0]

    async def update_employee(self, membership_id: uuid.UUID, data: EmployeeUpdate) -> EmployeeOut:
        row = (
            await self.db.execute(
                select(Membership, Role)
                .join(
                    Role, (Role.tenant_id == Membership.tenant_id) & (Role.id == Membership.role_id)
                )
                .where(
                    Membership.tenant_id == self.tenant_id,
                    Membership.id == membership_id,
                    Membership.status != "revoked",
                )
                .with_for_update(of=Membership)
            )
        ).first()
        if row is None:
            raise NotFoundError("Employee not found")
        membership, current_role = row
        if membership.user_id == self.access.user_id:
            raise ForbiddenError("You cannot change your own access", code="CANNOT_MODIFY_SELF")
        if _is_owner(current_role) and self.access.role_code != OWNER_ROLE_CODE:
            raise ForbiddenError("Only an owner can change an owner", code="OWNER_ONLY")
        changes: dict = {}
        if data.role_id is not None and data.role_id != membership.role_id:
            role = await self._role(data.role_id)
            await self._assignable(role)
            membership.role_id = role.id
            changes["role"] = role.code
        if data.status is not None and data.status != membership.status:
            membership.status = data.status
            changes["status"] = data.status
        if data.restricted_to_branches is False:
            membership.restricted_to_branches = False
            await self._set_branches(membership, [])
            changes["branches"] = "all"
        elif data.branch_ids is not None or data.restricted_to_branches:
            await self._branches(data.branch_ids or [])
            membership.restricted_to_branches = True
            await self._set_branches(membership, data.branch_ids or [])
            changes["branches"] = [str(b) for b in data.branch_ids or []]
        await self.db.flush()
        if changes:
            audit(
                self.db, self.access, "employee.updated", "membership", membership.id, None, changes
            )
        return (await self.list_employees(membership.id))[0]

    async def remove_employee(self, membership_id: uuid.UUID) -> None:
        await self.update_employee(membership_id, EmployeeUpdate())  # same guards
        membership = (
            await self.db.execute(
                select(Membership).where(
                    Membership.tenant_id == self.tenant_id, Membership.id == membership_id
                )
            )
        ).scalar_one()
        membership.status = "revoked"
        await self.db.flush()
        audit(self.db, self.access, "employee.removed", "membership", membership.id)

    # ── company settings ──

    async def get_settings(self) -> SettingsOut:
        tenant = (
            await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        ).scalar_one()
        await self.db.refresh(tenant)
        cs = await get_company_settings(self.db, self.tenant_id)
        await self.db.refresh(cs)
        return SettingsOut(
            name=tenant.name,
            slug=tenant.slug,
            legal_name=tenant.legal_name,
            email=tenant.email,
            phone=tenant.phone,
            address=tenant.address,
            currency=tenant.currency,
            timezone=tenant.timezone,
            tax_number=cs.tax_number,
            default_tax_rate=cs.default_tax_rate,
            allow_negative_stock=cs.allow_negative_stock,
            invoice_footer=cs.invoice_footer,
        )

    async def update_settings(self, data: SettingsUpdate) -> SettingsOut:
        values = data.model_dump(exclude_unset=True)
        if "timezone" in values:
            try:
                ZoneInfo(values["timezone"])
            except Exception:  # noqa: BLE001
                raise AppError("Unknown time zone", code="INVALID_TIMEZONE") from None
        for required in (
            "name",
            "currency",
            "timezone",
            "default_tax_rate",
            "allow_negative_stock",
        ):
            if required in values and values[required] is None:
                values.pop(required)
        tenant = (
            await self.db.execute(
                select(Tenant).where(Tenant.id == self.tenant_id).with_for_update()
            )
        ).scalar_one()
        cs = await get_company_settings(self.db, self.tenant_id)
        company_fields = {
            "tax_number",
            "default_tax_rate",
            "allow_negative_stock",
            "invoice_footer",
        }
        for name, value in values.items():
            if isinstance(value, str):
                value = value or None  # empty string clears an optional field
            setattr(cs if name in company_fields else tenant, name, value)
        await self.db.flush()
        audit(
            self.db,
            self.access,
            "settings.updated",
            "company",
            self.tenant_id,
            None,
            {"fields": sorted(values)},
        )
        return await self.get_settings()
