from tests.api_helpers import (
    API,
    add_member,
    adjust,
    create_product,
    login,
    main_warehouse,
    register_company,
)
from tests.factories import unique


async def test_product_lifecycle_and_validation(app):
    o = await register_company(app)
    c, h = o.client, o.h
    cat = (await c.post(f"{API}/categories", headers=h, json={"name": "مشروبات"})).json()["data"]
    unit = (
        await c.post(f"{API}/units", headers=h, json={"name": "قطعة", "abbreviation": "pc"})
    ).json()["data"]
    p = await create_product(
        o,
        name="عصير برتقال",
        sku="jc-001",
        barcode="6221234567890",
        category_id=cat["id"],
        unit_id=unit["id"],
        purchase_price="7.5000",
        selling_price="12.50",
        tax_rate="14",
    )
    assert p["sku"] == "JC-001" and p["selling_price"] == "12.50" and p["average_cost"] == "0.0000"

    bad = [
        {"name": "x", "sku": "N1", "selling_price": "-1"},
        {"name": "x", "sku": "N2", "tax_rate": "101"},
        {"name": "x", "sku": "N3", "selling_price": "1.999"},
        {"name": "x", "sku": "N4", "average_cost": "1"},  # not client-writable
        {"name": "x", "sku": "N5", "tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"name": "", "sku": "N6"},
    ]
    for body in bad:
        assert (await c.post(f"{API}/products", headers=h, json=body)).status_code == 422, body
    r = await c.patch(f"{API}/products/{p['id']}", headers=h, json={"average_cost": "1"})
    assert r.status_code == 422

    dup = await c.post(f"{API}/products", headers=h, json={"name": "y", "sku": "JC-001"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "SKU_TAKEN"
    dup = await c.post(
        f"{API}/products",
        headers=h,
        json={"name": "y", "sku": "JC-002", "barcode": "6221234567890"},
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "BARCODE_TAKEN"

    async def found(**params):
        r = await c.get(f"{API}/products", headers=h, params=params)
        return [i["sku"] for i in r.json()["data"]["items"]]

    await create_product(o, name="شاي أخضر", sku="TEA-1")
    assert await found(q="برتقال") == ["JC-001"]
    assert await found(q="jc-0") == ["JC-001"]
    assert await found(q="62212345") == ["JC-001"]
    assert await found(barcode="6221234567890") == ["JC-001"]
    assert await found(category_id=cat["id"]) == ["JC-001"]
    assert await found(sort="sku") == ["JC-001", "TEA-1"]

    r = await c.patch(
        f"{API}/products/{p['id']}", headers=h, json={"selling_price": "15.00", "barcode": None}
    )
    assert r.json()["data"]["selling_price"] == "15.00" and r.json()["data"]["barcode"] is None
    r = await c.patch(f"{API}/products/{p['id']}", headers=h, json={"is_active": False})
    assert r.json()["data"]["is_active"] is False
    assert await found(is_active=True) == ["TEA-1"]


async def test_sku_is_unique_per_company_not_globally_and_references_are_tenant_checked(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    await create_product(a, sku="SHARED-1")
    await create_product(b, sku="SHARED-1")  # allowed: different company
    b_cat = (await b.client.post(f"{API}/categories", headers=b.h, json={"name": "B cat"})).json()[
        "data"
    ]
    b_prod = await create_product(b)

    r = await a.client.post(
        f"{API}/products", headers=a.h, json={"name": "x", "sku": "X1", "category_id": b_cat["id"]}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REFERENCE"
    assert (await a.client.get(f"{API}/products/{b_prod['id']}", headers=a.h)).status_code == 404
    assert (
        await a.client.patch(f"{API}/products/{b_prod['id']}", headers=a.h, json={"name": "h"})
    ).status_code == 404
    assert (await a.client.delete(f"{API}/products/{b_prod['id']}", headers=a.h)).status_code == 404
    skus = (await a.client.get(f"{API}/products", headers=a.h)).json()["data"]
    assert skus["total"] == 1


async def test_product_with_history_cannot_be_deleted_only_deactivated(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    fresh, used = await create_product(o), await create_product(o)
    assert (await adjust(o, wh, used["id"], 5)).status_code == 201

    assert (await o.client.delete(f"{API}/products/{fresh['id']}", headers=o.h)).status_code == 200
    r = await o.client.delete(f"{API}/products/{used['id']}", headers=o.h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRODUCT_IN_USE"
    detail = (await o.client.get(f"{API}/products/{used['id']}", headers=o.h)).json()["data"]
    assert detail["total_stock"] == "5.000" and detail["stock"][0]["warehouse_id"] == wh


async def test_catalog_permissions(app):
    o = await register_company(app)
    cashier = await login(app, await add_member(o, "sales_cashier"))
    accountant = await login(app, await add_member(o, "accountant"))
    body = {"name": "x", "sku": unique("s")}
    assert (await cashier.client.get(f"{API}/products", headers=cashier.h)).status_code == 200
    assert (
        await cashier.client.post(f"{API}/products", headers=cashier.h, json=body)
    ).status_code == 403
    assert (
        await cashier.client.post(f"{API}/categories", headers=cashier.h, json={"name": "c"})
    ).status_code == 403
    assert (await accountant.client.get(f"{API}/products", headers=accountant.h)).status_code == 403
