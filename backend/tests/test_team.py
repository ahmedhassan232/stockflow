import re

from app.core import email as email_module
from tests.api_helpers import API, PASSWORD, add_member, login, new_client, register_company
from tests.factories import unique


async def roles(o):
    return {r["code"]: r for r in (await o.client.get(f"{API}/roles", headers=o.h)).json()["data"]}


async def invite(acc, role_id, email=None, **extra):
    return await acc.client.post(
        f"{API}/employees",
        headers=acc.h,
        json={
            "full_name": "New Hire",
            "email": email or f"{unique('hire')}@example.com",
            "role_id": role_id,
            **extra,
        },
    )


async def employees(o):
    return (await o.client.get(f"{API}/employees", headers=o.h)).json()["data"]


async def test_invite_flow_sets_password_and_grants_role_permissions(app):
    o = await register_company(app, "Nile Trading")
    r = await roles(o)
    email = f"{unique('cashier')}@example.com"
    res = await invite(o, r["sales_cashier"]["id"], email)
    assert res.status_code == 201, res.text
    emp = res.json()["data"]
    assert (emp["role_code"], emp["status"], emp["has_password"]) == (
        "sales_cashier",
        "active",
        False,
    )

    # cannot sign in before choosing a password
    c = new_client(app)
    assert (
        await c.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    ).status_code == 401
    mail = email_module.outbox[-1]
    assert mail.to == email and "Nile Trading" in mail.body
    token = re.search(r"token=([\w-]+)", mail.body).group(1)
    r2 = await c.post(f"{API}/auth/reset-password", json={"token": token, "new_password": PASSWORD})
    assert r2.status_code == 200, r2.text
    hire = await login(app, email)
    assert hire.tenant_id == o.tenant_id
    assert (await hire.client.get(f"{API}/products", headers=hire.h)).status_code == 200
    assert (await hire.client.get(f"{API}/employees", headers=hire.h)).status_code == 403

    dup = await invite(o, r["sales_cashier"]["id"], email.upper())
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "ALREADY_MEMBER"


async def test_suspend_and_remove_take_effect_immediately(app):
    o = await register_company(app)
    emp_acc = await login(app, await add_member(o, "inventory_manager"))
    emp = next(e for e in await employees(o) if e["user_id"] == str(emp_acc.user_id))
    assert (await emp_acc.client.get(f"{API}/products", headers=emp_acc.h)).status_code == 200

    r = await o.client.patch(
        f"{API}/employees/{emp['id']}", headers=o.h, json={"status": "suspended"}
    )
    assert r.json()["data"]["status"] == "suspended"
    blocked = await emp_acc.client.get(
        f"{API}/products", headers=emp_acc.h
    )  # same, still-valid token
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "MEMBERSHIP_INACTIVE"

    await o.client.patch(f"{API}/employees/{emp['id']}", headers=o.h, json={"status": "active"})
    r = await o.client.patch(
        f"{API}/employees/{emp['id']}",
        headers=o.h,
        json={"role_id": (await roles(o))["accountant"]["id"]},
    )
    assert r.json()["data"]["role_code"] == "accountant"
    assert (
        await emp_acc.client.get(f"{API}/products", headers=emp_acc.h)
    ).status_code == 403  # role changed

    assert (await o.client.delete(f"{API}/employees/{emp['id']}", headers=o.h)).status_code == 200
    assert (await emp_acc.client.get(f"{API}/sales", headers=emp_acc.h)).status_code == 403
    assert str(emp_acc.user_id) not in {e["user_id"] for e in await employees(o)}


async def test_privilege_escalation_is_blocked(app):
    o = await register_company(app)
    r = await roles(o)
    admin = await login(app, await add_member(o, "admin"))
    people = await employees(o)
    owner_m = next(e for e in people if e["role_code"] == "owner")
    admin_m = next(e for e in people if e["user_id"] == str(admin.user_id))

    res = await invite(admin, r["owner"]["id"])  # admin cannot mint an owner
    assert res.status_code == 403 and res.json()["error"]["code"] == "OWNER_ONLY"
    res = await admin.client.patch(
        f"{API}/employees/{owner_m['id']}", headers=admin.h, json={"status": "suspended"}
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "OWNER_ONLY"
    res = await admin.client.patch(
        f"{API}/employees/{admin_m['id']}", headers=admin.h, json={"role_id": r["owner"]["id"]}
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "CANNOT_MODIFY_SELF"
    res = await o.client.patch(
        f"{API}/employees/{owner_m['id']}", headers=o.h, json={"status": "suspended"}
    )
    assert res.status_code == 403  # the owner cannot lock themselves out either
    assert (
        await admin.client.delete(f"{API}/employees/{owner_m['id']}", headers=admin.h)
    ).status_code == 403

    # admin lacks roles.manage / settings.update
    body = {"name": "Super", "permissions": ["roles.manage"]}
    assert (await admin.client.post(f"{API}/roles", headers=admin.h, json=body)).status_code == 403
    assert (
        await admin.client.patch(f"{API}/settings", headers=admin.h, json={"name": "Hacked"})
    ).status_code == 403
    # …and cannot hand out a role that holds permissions the admin does not have
    strong = (await o.client.post(f"{API}/roles", headers=o.h, json=body)).json()["data"]
    res = await invite(admin, strong["id"])
    assert res.status_code == 403 and res.json()["error"]["code"] == "PRIVILEGE_ESCALATION"
    assert (await invite(admin, r["sales_cashier"]["id"])).status_code == 201

    cashier = await login(app, await add_member(o, "sales_cashier"))
    assert (await invite(cashier, r["sales_cashier"]["id"])).status_code == 403


async def test_custom_roles(app):
    o = await register_company(app)
    r = await o.client.post(
        f"{API}/roles",
        headers=o.h,
        json={"name": "Stock Viewer", "permissions": ["products.view", "inventory.view"]},
    )
    assert r.status_code == 201, r.text
    role = r.json()["data"]
    assert role["is_system"] is False and role["permissions"] == ["inventory.view", "products.view"]
    bad = await o.client.post(
        f"{API}/roles", headers=o.h, json={"name": "Bad", "permissions": ["root.everything"]}
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_PERMISSION"

    email = f"{unique('viewer')}@example.com"
    await invite(o, role["id"], email)
    token = re.search(r"token=([\w-]+)", email_module.outbox[-1].body).group(1)
    await new_client(app).post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": PASSWORD}
    )
    viewer = await login(app, email)
    assert (await viewer.client.get(f"{API}/inventory", headers=viewer.h)).status_code == 200
    assert (await viewer.client.get(f"{API}/sales", headers=viewer.h)).status_code == 403

    upd = await o.client.put(
        f"{API}/roles/{role['id']}",
        headers=o.h,
        json={"name": "Stock Viewer", "permissions": ["sales.view"]},
    )
    assert upd.json()["data"]["permissions"] == ["sales.view"]
    assert (
        await viewer.client.get(f"{API}/inventory", headers=viewer.h)
    ).status_code == 403  # immediate
    assert (await viewer.client.get(f"{API}/sales", headers=viewer.h)).status_code == 200

    in_use = await o.client.delete(f"{API}/roles/{role['id']}", headers=o.h)
    assert in_use.status_code == 409 and in_use.json()["error"]["code"] == "ROLE_IN_USE"
    all_roles = await roles(o)
    owner_role = all_roles["owner"]
    res = await o.client.put(
        f"{API}/roles/{owner_role['id']}", headers=o.h, json={"name": "x2", "permissions": []}
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "OWNER_ROLE_IMMUTABLE"
    assert (
        await o.client.delete(f"{API}/roles/{all_roles['admin']['id']}", headers=o.h)
    ).status_code == 409
    empty = (
        await o.client.post(f"{API}/roles", headers=o.h, json={"name": "Temp", "permissions": []})
    ).json()["data"]
    assert (await o.client.delete(f"{API}/roles/{empty['id']}", headers=o.h)).status_code == 200


async def test_team_and_settings_are_isolated_between_companies(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    b_roles, b_people = await roles(b), await employees(b)
    b_branch = (await b.client.get(f"{API}/branches", headers=b.h)).json()["data"]["items"][0]["id"]
    assert (await invite(a, b_roles["admin"]["id"])).status_code == 404  # B's role
    a_roles = await roles(a)
    res = await invite(a, a_roles["admin"]["id"], branch_ids=[b_branch])  # B's branch
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_REFERENCE"
    assert (
        await a.client.patch(
            f"{API}/employees/{b_people[0]['id']}", headers=a.h, json={"status": "suspended"}
        )
    ).status_code == 404
    assert (
        await a.client.put(
            f"{API}/roles/{b_roles['admin']['id']}",
            headers=a.h,
            json={"name": "xx", "permissions": []},
        )
    ).status_code == 404
    assert len(await employees(a)) == 1 and {r["id"] for r in a_roles.values()}.isdisjoint(
        r["id"] for r in b_roles.values()
    )

    r = await a.client.patch(
        f"{API}/settings",
        headers=a.h,
        json={
            "name": "Alpha Renamed",
            "default_tax_rate": "14",
            "allow_negative_stock": True,
            "timezone": "Africa/Cairo",
            "invoice_footer": "شكراً",
        },
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["data"]["name"] == "Alpha Renamed"
        and r.json()["data"]["default_tax_rate"] == "14.00"
    )
    untouched = (await b.client.get(f"{API}/settings", headers=b.h)).json()["data"]
    assert untouched["name"] == "Beta Co" and untouched["allow_negative_stock"] is False
    for bad in ({"timezone": "Mars/Olympus"},):
        assert (await a.client.patch(f"{API}/settings", headers=a.h, json=bad)).status_code == 400
    for bad in (
        {"currency": "egp"},
        {"default_tax_rate": "101"},
        {"slug": "x"},
        {"status": "active"},
    ):
        assert (await a.client.patch(f"{API}/settings", headers=a.h, json=bad)).status_code == 422
