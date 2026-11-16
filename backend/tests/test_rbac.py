"""Phase 3 acceptance over HTTP: tenant isolation, company selection, permissions and
branch restrictions – all decided by the backend on every request."""

import uuid

from sqlalchemy import text

from app.db.tenant import TenantContext, context_transaction
from app.modules.auth import security
from app.modules.authorization.permissions import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from tests.api_helpers import API, add_member, bearer, login, register_company


async def _branch(account, **params):
    r = await account.client.get(f"{API}/branches", headers=account.h, params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _create_branch(account, code: str, name: str = "Branch"):
    r = await account.client.post(
        f"{API}/branches", headers=account.h, json={"name": name, "code": code}
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ───────────────────────── tenant isolation over HTTP ─────────────────────────


async def test_company_a_cannot_read_or_modify_company_b_over_http(app):
    a, b = await register_company(app, "Alpha"), await register_company(app, "Beta")
    b_branch = (await _branch(b))["items"][0]
    b_wh = (await b.client.get(f"{API}/warehouses", headers=b.h)).json()["data"]["items"][0]

    listing = await _branch(a)
    assert listing["total"] == 1 and listing["items"][0]["id"] != b_branch["id"]

    c = a.client
    assert (await c.get(f"{API}/branches/{b_branch['id']}", headers=a.h)).status_code == 404
    assert (
        await c.patch(f"{API}/branches/{b_branch['id']}", headers=a.h, json={"name": "hacked"})
    ).status_code == 404
    assert (await c.get(f"{API}/warehouses/{b_wh['id']}", headers=a.h)).status_code == 404
    assert (
        await c.patch(f"{API}/warehouses/{b_wh['id']}", headers=a.h, json={"name": "hacked"})
    ).status_code == 404
    # Referencing B's branch from A's new warehouse is refused as "not found".
    r = await c.post(
        f"{API}/warehouses",
        headers=a.h,
        json={"name": "Leak", "code": "LEAK", "branch_id": b_branch["id"]},
    )
    assert r.status_code == 404
    assert (await _branch(b))["items"][0]["name"] == b_branch["name"]


async def test_client_supplied_tenant_id_is_never_accepted(app):
    a, b = await register_company(app, "Alpha"), await register_company(app, "Beta")
    c = a.client
    r = await c.post(
        f"{API}/branches",
        headers=a.h,
        json={"name": "X", "code": "X1", "tenant_id": str(b.tenant_id)},
    )
    assert r.status_code == 422
    # Headers / query parameters naming another tenant change nothing.
    r = await c.get(
        f"{API}/branches",
        headers={**a.h, "X-Tenant-ID": str(b.tenant_id)},
        params={"tenant_id": str(b.tenant_id)},
    )
    ids = {i["id"] for i in r.json()["data"]["items"]}
    assert ids == {i["id"] for i in (await _branch(a))["items"]}


async def test_cannot_select_a_company_without_membership(app):
    a, b = await register_company(app, "Alpha"), await register_company(app, "Beta")
    r = await a.client.post(
        f"{API}/auth/select-company", headers=a.h, json={"tenant_id": str(b.tenant_id)}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_A_MEMBER"
    r = await a.client.post(
        f"{API}/auth/select-company", headers=a.h, json={"tenant_id": str(uuid.uuid4())}
    )
    assert r.status_code == 403


async def test_validly_signed_token_for_foreign_tenant_is_still_refused(app):
    """Even if a token naming Company B were ever issued to A's user (a bug elsewhere),
    the per-request membership check refuses it."""
    a, b = await register_company(app, "Alpha"), await register_company(app, "Beta")
    session_id = (await a.client.get(f"{API}/auth/sessions", headers=a.h)).json()["data"][0]["id"]
    forged, _ = security.create_access_token(
        user_id=a.user_id, session_id=uuid.UUID(session_id), tenant_id=b.tenant_id
    )
    r = await a.client.get(f"{API}/branches", headers=bearer(forged))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_A_MEMBER"


async def test_user_with_two_companies_must_choose_and_can_switch(app):
    a, b = await register_company(app, "Alpha"), await register_company(app, "Beta")
    shared = await add_member(a, "admin")
    async with context_transaction(b.ctx) as s:  # same person joins Beta as cashier
        await s.execute(
            text(
                "INSERT INTO memberships (tenant_id, user_id, role_id) "
                "SELECT :t, u.id, r.id FROM users u, roles r WHERE u.email = :e AND r.code = "
                "'sales_cashier'"
            ),
            {"t": b.tenant_id, "e": shared},
        )

    user = await login(app, shared)
    assert user.tenant_id is None
    c = user.client
    r = await c.get(f"{API}/branches", headers=user.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NO_ACTIVE_COMPANY"
    me = (await c.get(f"{API}/auth/me", headers=user.h)).json()["data"]
    assert {m["tenant_name"] for m in me["memberships"]} == {"Alpha", "Beta"}

    async def select(tenant_id):
        r = await c.post(
            f"{API}/auth/select-company", headers=user.h, json={"tenant_id": str(tenant_id)}
        )
        assert r.status_code == 200
        return bearer(r.json()["data"]["access_token"])

    in_a = await select(a.tenant_id)
    assert (
        await c.post(f"{API}/branches", headers=in_a, json={"name": "N", "code": "N1"})
    ).status_code == 201
    in_b = await select(b.tenant_id)
    assert (
        await c.post(f"{API}/branches", headers=in_b, json={"name": "N", "code": "N1"})
    ).status_code == 403
    assert (await c.get(f"{API}/branches", headers=in_b)).json()["data"]["total"] == 1
    # The selection is remembered by the session across a refresh.
    refreshed = (await c.post(f"{API}/auth/refresh")).json()["data"]
    assert refreshed["active_tenant_id"] == str(b.tenant_id)


async def test_revoked_membership_and_suspended_company_block_existing_tokens(app):
    owner = await register_company(app)
    employee = await login(app, await add_member(owner, "admin"))
    assert (await employee.client.get(f"{API}/branches", headers=employee.h)).status_code == 200

    async with context_transaction(owner.ctx) as s:
        await s.execute(
            text("UPDATE memberships SET status = 'revoked' WHERE user_id = :u"),
            {"u": employee.user_id},
        )
    r = await employee.client.get(f"{API}/branches", headers=employee.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "MEMBERSHIP_INACTIVE"
    # After a refresh the dead company is no longer selected.
    assert (await employee.client.post(f"{API}/auth/refresh")).json()["data"][
        "active_tenant_id"
    ] is None

    async with context_transaction(owner.ctx) as s:
        await s.execute(text("UPDATE tenants SET status = 'suspended'"))
    r = await owner.client.get(f"{API}/branches", headers=owner.h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "TENANT_SUSPENDED"


# ───────────────────────── permissions ─────────────────────────


async def test_permission_catalogue_matches_database_and_is_read_only():
    async with context_transaction(TenantContext()) as s:
        codes = set((await s.execute(text("SELECT code FROM permissions"))).scalars().all())
    assert codes == set(ALL_PERMISSIONS)
    for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
        assert perms <= ALL_PERMISSIONS, role
    import pytest
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with context_transaction(TenantContext()) as s:
            await s.execute(text("INSERT INTO permissions VALUES ('evil.all', 'x')"))


async def test_roles_get_exactly_their_default_permissions(app):
    owner = await register_company(app)
    for role in ("sales_cashier", "accountant", "warehouse_employee"):
        member = await login(app, await add_member(owner, role))
        me = (await member.client.get(f"{API}/auth/me", headers=member.h)).json()["data"]
        assert set(me["active_company"]["permissions"]) == set(DEFAULT_ROLE_PERMISSIONS[role])
        assert me["active_company"]["role_code"] == role


async def test_unauthorized_roles_receive_403(app):
    owner = await register_company(app)
    cashier = await login(app, await add_member(owner, "sales_cashier"))
    warehouse_emp = await login(app, await add_member(owner, "warehouse_employee"))
    accountant = await login(app, await add_member(owner, "accountant"))
    new_branch = {"name": "B", "code": "B9"}
    new_wh = {"name": "W", "code": "W9"}

    assert (await cashier.client.get(f"{API}/branches", headers=cashier.h)).status_code == 200
    r = await cashier.client.post(f"{API}/branches", headers=cashier.h, json=new_branch)
    assert r.status_code == 403
    assert r.json()["error"] == {
        "code": "FORBIDDEN",
        "message": "You do not have permission to perform this action",
        "details": {"missing_permissions": ["branches.manage"]},
    }
    r = await warehouse_emp.client.post(f"{API}/warehouses", headers=warehouse_emp.h, json=new_wh)
    assert r.status_code == 403
    # Accountant has no warehouse access at all (default role definition).
    assert (
        await accountant.client.get(f"{API}/warehouses", headers=accountant.h)
    ).status_code == 403
    assert (
        await owner.client.post(f"{API}/branches", headers=owner.h, json=new_branch)
    ).status_code == 201


async def test_permission_changes_apply_to_existing_tokens_immediately(app):
    owner = await register_company(app)
    admin = await login(app, await add_member(owner, "admin"))
    assert (
        await admin.client.post(
            f"{API}/branches", headers=admin.h, json={"name": "A", "code": "A1"}
        )
    ).status_code == 201
    async with context_transaction(owner.ctx) as s:
        await s.execute(
            text("DELETE FROM role_permissions WHERE permission_code = 'branches.manage'")
        )
    r = await admin.client.post(
        f"{API}/branches", headers=admin.h, json={"name": "A", "code": "A2"}
    )
    assert r.status_code == 403


# ───────────────────────── branch restrictions ─────────────────────────


async def test_branch_restricted_employee_cannot_reach_other_branches(app):
    owner = await register_company(app)
    main = (await _branch(owner))["items"][0]
    second = await _create_branch(owner, "B2", "Second")
    r = await owner.client.post(
        f"{API}/warehouses",
        headers=owner.h,
        json={"name": "Second WH", "code": "W2", "branch_id": second["id"]},
    )
    second_wh = r.json()["data"]

    emp = await login(app, await add_member(owner, "admin", branch_ids=[uuid.UUID(main["id"])]))
    c, h = emp.client, emp.h
    me = (await c.get(f"{API}/auth/me", headers=h)).json()["data"]["active_company"]
    assert me["restricted_to_branches"] is True and me["branch_ids"] == [main["id"]]

    assert [b["id"] for b in (await _branch(emp))["items"]] == [main["id"]]
    whs = (await c.get(f"{API}/warehouses", headers=h)).json()["data"]["items"]
    assert {w["branch_id"] for w in whs} == {main["id"]}

    assert (await c.get(f"{API}/branches/{second['id']}", headers=h)).status_code == 404
    assert (
        await c.patch(f"{API}/branches/{second['id']}", headers=h, json={"name": "x"})
    ).status_code == 404
    assert (await c.get(f"{API}/warehouses/{second_wh['id']}", headers=h)).status_code == 404
    assert (await c.get(f"{API}/warehouses", headers=h, params={"branch_id": second["id"]})).json()[
        "data"
    ]["total"] == 0
    # Cannot create in, or move a warehouse to, a branch outside the assignment.
    r = await c.post(
        f"{API}/warehouses", headers=h, json={"name": "N", "code": "N1", "branch_id": second["id"]}
    )
    assert r.status_code == 404
    r = await c.patch(
        f"{API}/warehouses/{whs[0]['id']}", headers=h, json={"branch_id": second["id"]}
    )
    assert r.status_code == 404
    # Company-wide actions need company-wide scope even with the permission.
    r = await c.post(f"{API}/branches", headers=h, json={"name": "N", "code": "N2"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "BRANCH_SCOPE_REQUIRED"
    # Inside the assigned branch everything permitted still works.
    r = await c.post(
        f"{API}/warehouses", headers=h, json={"name": "Ok", "code": "OK1", "branch_id": main["id"]}
    )
    assert r.status_code == 201


async def test_restricted_member_with_no_branches_sees_nothing(app):
    owner = await register_company(app)
    emp = await login(app, await add_member(owner, "admin", branch_ids=[]))
    assert (await _branch(emp))["total"] == 0
    assert (await emp.client.get(f"{API}/warehouses", headers=emp.h)).json()["data"]["total"] == 0


# ───────────────────────── resource behaviour ─────────────────────────


async def test_branch_crud_validation_search_and_pagination(app):
    owner = await register_company(app)
    c, h = owner.client, owner.h
    for i in range(3):
        await _create_branch(owner, f"cai-{i}", f"Cairo {i}")
    dup = await c.post(f"{API}/branches", headers=h, json={"name": "Dup", "code": "CAI-0"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "CODE_TAKEN"
    assert (
        await c.post(f"{API}/branches", headers=h, json={"name": "", "code": "Z"})
    ).status_code == 422
    assert (
        await c.post(f"{API}/branches", headers=h, json={"name": "Z", "code": "bad code!"})
    ).status_code == 422

    page = await _branch(owner, q="cairo", page=2, page_size=2)
    assert page["total"] == 3 and page["page"] == 2 and len(page["items"]) == 1
    assert (await _branch(owner, q="100%_"))["total"] == 0  # wildcards are escaped
    assert (
        await c.get(f"{API}/branches", headers=h, params={"page_size": 1000})
    ).status_code == 422

    target = page["items"][0]["id"]
    r = await c.patch(
        f"{API}/branches/{target}", headers=h, json={"is_active": False, "phone": "0100"}
    )
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False
    assert (
        await c.patch(f"{API}/branches/{target}", headers=h, json={"code": "NEW"})
    ).status_code == 422
    assert (await _branch(owner, is_active=False))["total"] == 1
    assert (await c.get(f"{API}/branches/{uuid.uuid4()}", headers=h)).status_code == 404
    assert (await c.get(f"{API}/branches/not-a-uuid", headers=h)).status_code == 422


async def test_protected_routes_require_authentication(client):
    for method, path in (
        ("GET", "/branches"),
        ("POST", "/branches"),
        ("GET", "/warehouses"),
        ("GET", "/auth/me"),
        ("GET", "/auth/sessions"),
        ("POST", "/auth/select-company"),
    ):
        r = await client.request(method, f"{API}{path}", json={})
        assert r.status_code == 401, path
