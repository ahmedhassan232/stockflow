"""HTTP-level helpers: everything goes through the real API unless stated otherwise."""

import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select

from app.db.tenant import TenantContext, context_transaction
from app.modules.auth import security
from app.modules.authorization.models import Membership, MembershipBranch, Role
from app.modules.users.models import User
from tests.factories import unique

PASSWORD = "correct horse battery"
API = "/api/v1"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class Account:
    client: httpx.AsyncClient
    email: str
    token: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None

    @property
    def h(self) -> dict[str, str]:
        return bearer(self.token)

    @property
    def ctx(self) -> TenantContext:
        return TenantContext(tenant_id=self.tenant_id, user_id=self.user_id)


def new_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def register_company(app, name: str = "Acme") -> Account:
    client = new_client(app)
    email = f"{unique('owner')}@example.com"
    r = await client.post(
        f"{API}/auth/register",
        json={
            "full_name": f"{name} Owner",
            "email": email,
            "password": PASSWORD,
            "company": {"name": name, "slug": unique("co")},
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    return Account(
        client,
        email,
        d["access_token"],
        uuid.UUID(d["user"]["id"]),
        uuid.UUID(d["active_tenant_id"]),
    )


async def login(app, email: str, password: str = PASSWORD) -> Account:
    client = new_client(app)
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    tid = d["active_tenant_id"]
    return Account(
        client,
        email,
        d["access_token"],
        uuid.UUID(d["user"]["id"]),
        uuid.UUID(tid) if tid else None,
    )


async def add_member(
    owner: Account, role_code: str, *, branch_ids: list[uuid.UUID] | None = None
) -> str:
    """Creates an employee directly in the DB (employee endpoints arrive in Phase 4) and
    returns their e-mail. `branch_ids` not None → restricted to exactly those branches."""
    email = f"{unique(role_code)}@example.com"
    async with context_transaction(owner.ctx) as s:
        user = User(
            full_name=role_code, email=email, password_hash=await security.hash_password(PASSWORD)
        )
        s.add(user)
        await s.flush()
        role = (await s.execute(select(Role).where(Role.code == role_code))).scalar_one()
        m = Membership(
            tenant_id=owner.tenant_id,
            user_id=user.id,
            role_id=role.id,
            restricted_to_branches=branch_ids is not None,
        )
        s.add(m)
        await s.flush()
        for b in branch_ids or []:
            s.add(MembershipBranch(tenant_id=owner.tenant_id, membership_id=m.id, branch_id=b))
    return email


# ───────────── business helpers (all through the HTTP API) ─────────────


async def main_warehouse(account: Account) -> str:
    r = await account.client.get(f"{API}/warehouses", headers=account.h, params={"q": "MAIN"})
    return r.json()["data"]["items"][0]["id"]


async def create_product(account: Account, **over) -> dict:
    body = {"name": "Widget", "sku": unique("sku"), "selling_price": "100.00", **over}
    r = await account.client.post(f"{API}/products", headers=account.h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def adjust(account: Account, warehouse_id, product_id, quantity, direction="in", **kw):
    return await account.client.post(
        f"{API}/inventory/adjustments",
        headers={**account.h, **kw.pop("headers", {})},
        json={
            "warehouse_id": str(warehouse_id),
            "product_id": str(product_id),
            "direction": direction,
            "quantity": str(quantity),
            "reason": "test adjustment",
            **kw,
        },
    )


async def stock_of(account: Account, product_id, warehouse_id=None) -> str:
    params = {"product_id": str(product_id)}
    if warehouse_id:
        params["warehouse_id"] = str(warehouse_id)
    r = await account.client.get(f"{API}/inventory", headers=account.h, params=params)
    items = r.json()["data"]["items"]
    return items[0]["quantity"] if items else "0"
