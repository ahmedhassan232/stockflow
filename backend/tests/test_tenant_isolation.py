"""Phase 2 acceptance: Company A can never read, modify, delete or reference Company B's
data. Everything here runs as the real runtime role against real PostgreSQL."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_sessionmaker
from app.db.tenant import TenantContext, apply_context, context_transaction
from app.modules.authorization.models import Membership
from app.modules.authorization.repository import (
    MembershipRepository,
    RoleRepository,
    list_memberships_of_user,
)
from app.modules.organization.models import Branch, Warehouse
from app.modules.organization.repository import BranchRepository, WarehouseRepository
from tests.factories import create_company, create_user

TENANT_TABLES = ("roles", "memberships", "branches", "warehouses")


async def _count(session, table: str) -> int:
    return (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()


# ───────────────────────── READ ─────────────────────────


async def test_raw_sql_sees_only_own_tenant_rows(two_companies):
    """Unfiltered `SELECT *` (worst-case buggy query) still returns only own rows."""
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        for table in TENANT_TABLES:
            ids = (await s.execute(text(f"SELECT DISTINCT tenant_id FROM {table}"))).scalars().all()
            assert ids == [a.tenant_id], table
        tenants = (await s.execute(text("SELECT id FROM tenants"))).scalars().all()
        assert tenants == [a.tenant_id]
        # Even asking for B's row by primary key returns nothing.
        got = await s.execute(text("SELECT 1 FROM branches WHERE id = :i"), {"i": b.p.branch_id})
        assert got.first() is None


async def test_no_tenant_context_sees_nothing(two_companies):
    async with context_transaction(TenantContext()) as s:
        for table in (*TENANT_TABLES, "tenants"):
            assert await _count(s, table) == 0, table


async def test_repository_cannot_fetch_other_tenants_row(two_companies):
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        repo = BranchRepository(s, a.tenant_id)
        assert await repo.get(b.p.branch_id) is None
        assert [x.id for x in await repo.list()] == [a.p.branch_id]
        assert await repo.count() == 1


async def test_repository_with_wrong_tenant_id_is_still_blocked_by_rls(two_companies):
    """Layer independence: even a repository wrongly built with B's id returns nothing
    while the transaction context is A."""
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        assert await BranchRepository(s, b.tenant_id).list() == []
        assert await RoleRepository(s, b.tenant_id).get_by_code("owner") is None


# ───────────────────────── WRITE ─────────────────────────


async def test_cannot_update_other_tenants_rows(two_companies):
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        res = await s.execute(
            text("UPDATE branches SET name = 'hacked' WHERE id = :i"), {"i": b.p.branch_id}
        )
        assert res.rowcount == 0
        assert await BranchRepository(s, a.tenant_id).update(b.p.branch_id, {"name": "x"}) is False
        res = await s.execute(
            text("UPDATE tenants SET name = 'hacked' WHERE id = :i"), {"i": b.tenant_id}
        )
        assert res.rowcount == 0
    async with context_transaction(b.ctx) as s:
        branch = await BranchRepository(s, b.tenant_id).get(b.p.branch_id)
        assert branch.name == "الفرع الرئيسي"
        name = (await s.execute(text("SELECT name FROM tenants"))).scalar_one()
        assert name == "Beta Stores"


async def test_cannot_delete_other_tenants_rows(two_companies):
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        res = await s.execute(text("DELETE FROM warehouses"))  # no WHERE at all
        assert res.rowcount == 1  # only A's own warehouse
        assert await WarehouseRepository(s, a.tenant_id).delete(b.p.warehouse_id) is False
    async with context_transaction(b.ctx) as s:
        assert await WarehouseRepository(s, b.tenant_id).get(b.p.warehouse_id) is not None


async def test_cannot_insert_row_stamped_with_other_tenant(two_companies):
    a, b = two_companies
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with context_transaction(a.ctx) as s:
            await s.execute(
                text("INSERT INTO branches (tenant_id, name, code) VALUES (:t, 'x', 'X1')"),
                {"t": b.tenant_id},
            )


async def test_cannot_move_own_row_into_other_tenant(two_companies):
    a, b = two_companies
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with context_transaction(a.ctx) as s:
            await s.execute(
                text("UPDATE branches SET tenant_id = :t WHERE id = :i"),
                {"t": b.tenant_id, "i": a.p.branch_id},
            )


async def test_cannot_write_without_tenant_context(two_companies):
    a, _ = two_companies
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with context_transaction(TenantContext()) as s:
            await s.execute(
                text("INSERT INTO branches (tenant_id, name, code) VALUES (:t, 'x', 'X2')"),
                {"t": a.tenant_id},
            )


async def test_repository_add_overrides_caller_supplied_tenant(two_companies):
    a, b = two_companies
    async with context_transaction(a.ctx) as s:
        branch = await BranchRepository(s, a.tenant_id).add(
            Branch(tenant_id=b.tenant_id, name="Second", code="B2")
        )
        assert branch.tenant_id == a.tenant_id


async def test_tenants_cannot_be_deleted_by_runtime_role(two_companies):
    a, _ = two_companies
    async with context_transaction(a.ctx) as s:
        await s.execute(text("DELETE FROM warehouses"))
        await s.execute(text("DELETE FROM branches"))
        res = await s.execute(text("DELETE FROM tenants WHERE id = :i"), {"i": a.tenant_id})
        assert res.rowcount == 0


# ─────────────── CROSS-TENANT REFERENCES (composite FKs) ───────────────


async def test_warehouse_cannot_reference_other_tenants_branch(two_companies):
    a, b = two_companies
    with pytest.raises(IntegrityError, match="fk_warehouses_tenant_id_branch_id_branches"):
        async with context_transaction(a.ctx) as s:
            await WarehouseRepository(s, a.tenant_id).add(
                Warehouse(name="Leaky", code="LEAK", branch_id=b.p.branch_id)
            )


async def test_membership_cannot_use_other_tenants_role(two_companies):
    a, b = two_companies
    newcomer = await create_user()
    with pytest.raises(IntegrityError, match="fk_memberships_tenant_id_role_id_roles"):
        async with context_transaction(a.ctx) as s:
            await MembershipRepository(s, a.tenant_id).add(
                Membership(user_id=newcomer, role_id=b.p.owner_role_id)
            )


async def test_branch_manager_must_be_member_of_same_tenant(two_companies):
    a, b = two_companies
    with pytest.raises(IntegrityError, match="manager_membership_id"):
        async with context_transaction(a.ctx) as s:
            await BranchRepository(s, a.tenant_id).update(
                a.p.branch_id, {"manager_membership_id": b.p.owner_membership_id}
            )


async def test_same_codes_are_allowed_in_different_tenants_but_not_twice_in_one(two_companies):
    a, _ = two_companies  # both companies already have branch code MAIN
    with pytest.raises(IntegrityError, match="uq_branches_tenant_id_code"):
        async with context_transaction(a.ctx) as s:
            await BranchRepository(s, a.tenant_id).add(Branch(name="Dup", code="MAIN"))


# ───────────────────── CONNECTION POOL ─────────────────────


async def test_pooled_connection_does_not_leak_tenant_context(two_companies, settings):
    """Force every transaction onto ONE physical connection and prove the context of the
    previous transaction is gone, after both commit and rollback."""
    a, b = two_companies
    engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    pids = set()

    async def run(ctx: TenantContext | None, *, fail: bool = False):
        async with maker() as s:
            try:
                async with s.begin():
                    if ctx:
                        await apply_context(s, ctx)
                    pids.add((await s.execute(text("SELECT pg_backend_pid()"))).scalar_one())
                    seen = (await s.execute(text("SELECT tenant_id FROM branches"))).scalars().all()
                    if fail:
                        raise RuntimeError("boom")
                    return seen
            except RuntimeError:
                return None

    try:
        assert await run(a.ctx) == [a.tenant_id]
        assert await run(None) == []  # after COMMIT
        assert await run(b.ctx) == [b.tenant_id]
        await run(a.ctx, fail=True)
        assert await run(None) == []  # after ROLLBACK
        assert len(pids) == 1, "test must reuse a single pooled connection"
    finally:
        await engine.dispose()


async def test_context_is_lost_after_mid_request_commit_fail_closed(two_companies):
    """A stray commit drops the context; later queries see nothing instead of leaking."""
    a, _ = two_companies
    async with get_sessionmaker()() as s:
        await s.begin()
        await apply_context(s, a.ctx)
        assert await _count(s, "branches") == 1
        await s.commit()
        assert await _count(s, "branches") == 0  # new transaction, no context
        await s.rollback()


async def test_apply_context_requires_a_transaction(two_companies, settings):
    a, _ = two_companies
    engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(engine)() as s:
            with pytest.raises(RuntimeError):
                await apply_context(s, a.ctx)
    finally:
        await engine.dispose()


# ───────────────────── USER-LEVEL VISIBILITY ─────────────────────


async def test_user_sees_only_their_own_memberships_across_companies():
    shared_owner = await create_user("Multi-company owner")
    a = await create_company("Gamma One", owner_id=shared_owner)
    b = await create_company("Gamma Two", owner_id=shared_owner)
    other = await create_company("Unrelated Co")

    async with context_transaction(TenantContext(user_id=shared_owner)) as s:
        mine = await list_memberships_of_user(s, shared_owner)
        assert {m.tenant_id for m in mine} == {a.tenant_id, b.tenant_id}
        # Asking for someone else's memberships yields nothing.
        assert await list_memberships_of_user(s, other.owner_id) == []
        names = (await s.execute(text("SELECT name FROM tenants ORDER BY name"))).scalars().all()
        assert names == ["Gamma One", "Gamma Two"]
        # Membership visibility does NOT open the companies' business data.
        assert await _count(s, "branches") == 0
        assert await _count(s, "roles") == 0


async def test_user_context_cannot_modify_memberships(two_companies):
    a, _ = two_companies
    async with context_transaction(TenantContext(user_id=a.owner_id)) as s:
        res = await s.execute(text("UPDATE memberships SET status = 'revoked'"))
        assert res.rowcount == 0
        res = await s.execute(text("DELETE FROM memberships"))
        assert res.rowcount == 0


# ───────────────────── ROLE HARDENING ─────────────────────


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE branches DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE branches NO FORCE ROW LEVEL SECURITY",
        "DROP POLICY tenant_isolation ON branches",
        "TRUNCATE branches CASCADE",
        "SET row_security = off; SELECT count(*) FROM branches",
    ],
)
async def test_runtime_role_cannot_switch_rls_off(statement):
    with pytest.raises(DBAPIError):
        async with context_transaction(TenantContext()) as s:
            for part in statement.split(";"):
                await s.execute(text(part))


async def test_malformed_tenant_context_is_rejected_not_ignored():
    with pytest.raises(DBAPIError):
        async with context_transaction(TenantContext()) as s:
            await s.execute(text("SELECT set_config('app.tenant_id', 'not-a-uuid', true)"))
            await s.execute(text("SELECT count(*) FROM branches"))


async def test_random_tenant_id_sees_nothing(two_companies):
    async with context_transaction(TenantContext(tenant_id=uuid.uuid4())) as s:
        assert await _count(s, "branches") == 0
