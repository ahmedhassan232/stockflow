import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.core.exceptions import ConflictError, NotFoundError
from app.db.tenant import TenantContext, context_transaction
from app.modules.authorization.defaults import DEFAULT_ROLES
from app.modules.authorization.repository import MembershipRepository, RoleRepository
from app.modules.organization.repository import WarehouseRepository
from app.modules.tenants.schemas import TenantCreate
from app.modules.tenants.service import TenantProvisioningService
from tests.factories import create_company, create_user, unique


async def test_provisioning_creates_a_complete_company():
    company = await create_company("Delta Foods")
    async with context_transaction(company.ctx) as s:
        tenant = (await s.execute(text("SELECT currency, timezone, status FROM tenants"))).one()
        assert tuple(tenant) == ("EGP", "Africa/Cairo", "active")

        roles = await RoleRepository(s, company.tenant_id).list()
        assert {r.code for r in roles} == {code for code, _, _ in DEFAULT_ROLES}
        assert all(r.is_system for r in roles)

        membership = await MembershipRepository(s, company.tenant_id).get_for_user(company.owner_id)
        assert membership.status == "active"
        assert membership.role_id == company.p.owner_role_id

        warehouse = await WarehouseRepository(s, company.tenant_id).get(company.p.warehouse_id)
        assert warehouse.branch_id == company.p.branch_id


async def test_provisioning_is_atomic_when_a_late_step_fails(monkeypatch):
    """If creating the warehouse (the LAST step) fails, nothing at all is left behind."""
    owner = await create_user()
    slug = unique("atomic")

    async def explode(self, entity):
        raise RuntimeError("warehouse step failed")

    monkeypatch.setattr(WarehouseRepository, "add", explode)
    with pytest.raises(RuntimeError, match="warehouse step failed"):
        async with context_transaction(TenantContext(user_id=owner)) as s:
            await TenantProvisioningService(s).provision(
                owner_user_id=owner, data=TenantCreate(name="Atomic Co", slug=slug)
            )
    monkeypatch.undo()

    async with context_transaction(TenantContext(user_id=owner)) as s:
        assert (await s.execute(text("SELECT count(*) FROM memberships"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM tenants"))).scalar_one() == 0
    # The slug is free again, so the same registration now succeeds.
    async with context_transaction(TenantContext(user_id=owner)) as s:
        await TenantProvisioningService(s).provision(
            owner_user_id=owner, data=TenantCreate(name="Atomic Co", slug=slug)
        )


async def test_duplicate_slug_is_a_conflict_even_though_other_tenants_are_invisible():
    existing = await create_company("Original")
    owner = await create_user()
    with pytest.raises(ConflictError):
        async with context_transaction(TenantContext(user_id=owner)) as s:
            await TenantProvisioningService(s).provision(
                owner_user_id=owner,
                data=TenantCreate(name="Copycat", slug=existing.slug.upper()),  # case-insensitive
            )


async def test_unknown_or_inactive_owner_is_rejected():
    import uuid

    with pytest.raises(NotFoundError):
        async with context_transaction(TenantContext()) as s:
            await TenantProvisioningService(s).provision(
                owner_user_id=uuid.uuid4(), data=TenantCreate(name="Ghost", slug=unique("ghost"))
            )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "X Co", "slug": "Bad Slug!"},
        {"name": "X Co", "slug": "ok-slug", "currency": "EGPP"},
        {"name": "X Co", "slug": "ok-slug", "status": "active"},  # mass assignment
        {"name": "X Co", "slug": "ok-slug", "id": "11111111-1111-1111-1111-111111111111"},
        {"name": "X Co", "slug": "ok-slug", "tenant_id": "11111111-1111-1111-1111-111111111111"},
    ],
)
def test_tenant_create_rejects_invalid_or_privileged_fields(payload):
    with pytest.raises(ValidationError):
        TenantCreate(**payload)


async def test_updated_at_is_maintained_by_trigger():
    company = await create_company("Clock Co")
    async with context_transaction(company.ctx) as s:
        before = (await s.execute(text("SELECT updated_at FROM branches"))).scalar_one()
    async with context_transaction(company.ctx) as s:
        await s.execute(text("UPDATE branches SET name = 'Renamed'"))
        after = (await s.execute(text("SELECT updated_at FROM branches"))).scalar_one()
    assert after > before
