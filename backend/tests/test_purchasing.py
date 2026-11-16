import asyncio
import uuid
from decimal import Decimal

from tests.api_helpers import (
    API,
    add_member,
    adjust,
    create_product,
    login,
    main_warehouse,
    new_client,
    register_company,
    stock_of,
)


async def supplier(o, name="Delta Supplies"):
    r = await o.client.post(
        f"{API}/suppliers", headers=o.h, json={"name": name, "phone": "+20 100 000 0000"}
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def purchase(o, wh, lines, status="ordered", sup=None, expect=201):
    r = await o.client.post(
        f"{API}/purchases",
        headers=o.h,
        json={
            "supplier_id": sup or await supplier(o),
            "warehouse_id": wh,
            "status": status,
            "items": [
                {"product_id": p, "quantity": str(q), "unit_cost": str(c), **extra}
                for p, q, c, *rest in lines
                for extra in [rest[0] if rest else {}]
            ],
        },
    )
    assert r.status_code == expect, r.text
    return r.json().get("data")


async def receive(o, po_id, items=None, **headers):
    body = (
        {} if items is None else {"items": [{"item_id": i, "quantity": str(q)} for i, q in items]}
    )
    return await o.client.post(
        f"{API}/purchases/{po_id}/receive", headers={**o.h, **headers}, json=body
    )


async def avg_cost(o, product_id):
    return (await o.client.get(f"{API}/products/{product_id}", headers=o.h)).json()["data"][
        "average_cost"
    ]


async def test_purchase_totals_are_computed_by_the_server(app):
    o = await register_company(app)
    wh, p1, p2 = await main_warehouse(o), await create_product(o), await create_product(o)
    po = await purchase(
        o, wh, [(p1["id"], 10, "7.5000", {"tax_rate": "14"}), (p2["id"], "2.500", "3.3333")]
    )
    assert po["number"] == "PO-000001" and po["status"] == "ordered"
    # 10×7.5 = 75.00 (+14% = 10.50) ; 2.5×3.3333 = 8.33325 → 8.33
    assert (po["subtotal"], po["tax_amount"], po["total"]) == ("83.33", "10.50", "93.83")
    assert po["balance_due"] == "93.83"
    assert await stock_of(o, p1["id"]) in ("0", "0.000")  # ordering does not change stock

    r = await o.client.post(
        f"{API}/purchases",
        headers=o.h,
        json={
            "supplier_id": po["supplier_id"],
            "warehouse_id": wh,
            "total": "1.00",
            "items": [{"product_id": p1["id"], "quantity": "1", "unit_cost": "1"}],
        },
    )
    assert r.status_code == 422  # client cannot send totals
    await purchase(o, wh, [(p1["id"], 1, 1), (p1["id"], 1, 1)], expect=422)
    await purchase(o, wh, [(p1["id"], 0, 1)], expect=422)
    await purchase(o, wh, [(p1["id"], 1, -1)], expect=422)


async def test_receiving_updates_stock_ledger_and_weighted_average_cost(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    first = await purchase(o, wh, [(p["id"], 10, "10.0000")])
    assert (await receive(o, first["id"])).json()["data"]["status"] == "received"
    assert await stock_of(o, p["id"]) == "10.000" and await avg_cost(o, p["id"]) == "10.0000"

    second = await purchase(o, wh, [(p["id"], 30, "14.0000")])
    await receive(o, second["id"])
    # (10×10 + 30×14) / 40 = 13
    assert await stock_of(o, p["id"]) == "40.000" and await avg_cost(o, p["id"]) == "13.0000"

    third = await purchase(o, wh, [(p["id"], 3, "20.0000")])
    await receive(o, third["id"])
    # (40×13 + 3×20) / 43 = 13.488372… → 13.4884
    assert await avg_cost(o, p["id"]) == "13.4884"

    moves = (
        await o.client.get(
            f"{API}/inventory/movements", headers=o.h, params={"product_id": p["id"]}
        )
    ).json()["data"]["items"]
    assert [(m["movement_type"], m["quantity_in"], m["unit_cost"]) for m in moves] == [
        ("purchase_receipt", "3.000", "20.0000"),
        ("purchase_receipt", "30.000", "14.0000"),
        ("purchase_receipt", "10.000", "10.0000"),
    ]
    assert all(m["reference_type"] == "purchase_receipt" for m in moves)


async def test_partial_receipt_and_over_receipt(app):
    o = await register_company(app)
    wh, p1, p2 = await main_warehouse(o), await create_product(o), await create_product(o)
    po = await purchase(o, wh, [(p1["id"], 10, 5), (p2["id"], 4, 2)])
    i1, i2 = (i["id"] for i in po["items"])

    r = await receive(o, po["id"], [(i1, 6)])
    assert r.json()["data"]["status"] == "partially_received"
    assert await stock_of(o, p1["id"]) == "6.000"

    r = await receive(o, po["id"], [(i1, 5)])  # only 4 outstanding
    assert r.status_code == 409 and r.json()["error"]["code"] == "OVER_RECEIPT"
    r = await receive(o, po["id"], [(i2, 4), (i1, 5)])  # atomic: valid line is not applied either
    assert r.status_code == 409 and await stock_of(o, p2["id"]) in ("0", "0.000")
    assert (await receive(o, po["id"], [(str(uuid.uuid4()), 1)])).status_code == 400

    r = await receive(o, po["id"])  # everything outstanding
    data = r.json()["data"]
    assert data["status"] == "received"
    assert [i["received_quantity"] for i in data["items"]] == ["10.000", "4.000"]
    assert await stock_of(o, p1["id"]) == "10.000" and await stock_of(o, p2["id"]) == "4.000"
    r = await receive(o, po["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS"


async def test_duplicate_and_concurrent_receipts_cannot_double_stock(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    po = await purchase(o, wh, [(p["id"], 10, 5)])
    key = {"Idempotency-Key": f"rcv-{uuid.uuid4()}"}
    a, b = await receive(o, po["id"], **key), await receive(o, po["id"], **key)
    assert a.status_code == b.status_code == 200 and b.json()["data"]["idempotent_replay"] is True
    assert await stock_of(o, p["id"]) == "10.000"

    po2 = await purchase(o, wh, [(p["id"], 7, 5)])
    results = await asyncio.gather(
        *[  # no idempotency key: the PO row lock must protect us
            new_client(app).post(f"{API}/purchases/{po2['id']}/receive", headers=o.h, json={})
            for _ in range(6)
        ]
    )
    assert sorted(r.status_code for r in results) == [200] + [409] * 5
    assert await stock_of(o, p["id"]) == "17.000"


async def test_draft_cancel_and_status_rules(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    draft = await purchase(o, wh, [(p["id"], 1, 1)], status="draft")
    assert (await receive(o, draft["id"])).status_code == 409  # drafts cannot receive
    r = await o.client.post(f"{API}/purchases/{draft['id']}/confirm", headers=o.h)
    assert r.json()["data"]["status"] == "ordered"
    r = await o.client.post(f"{API}/purchases/{draft['id']}/cancel", headers=o.h)
    assert r.json()["data"]["status"] == "cancelled"
    assert (await receive(o, draft["id"])).status_code == 409

    po = await purchase(o, wh, [(p["id"], 1, 1)])
    await receive(o, po["id"])
    r = await o.client.post(f"{API}/purchases/{po['id']}/cancel", headers=o.h)
    assert r.status_code == 409  # received goods must be returned, not cancelled


async def test_purchase_return_and_payments(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    po = await purchase(o, wh, [(p["id"], 10, "8.0000")])
    item = po["items"][0]["id"]
    await receive(o, po["id"])

    async def ret(q):
        return await o.client.post(
            f"{API}/purchases/{po['id']}/returns",
            headers=o.h,
            json={"items": [{"item_id": item, "quantity": str(q)}], "reason": "damaged goods"},
        )

    r = await ret(4)
    assert r.status_code == 200 and r.json()["data"]["items"][0]["returned_quantity"] == "4.000"
    assert await stock_of(o, p["id"]) == "6.000"
    r = await ret(7)
    assert r.status_code == 409 and r.json()["error"]["code"] == "OVER_RETURN"
    await adjust(o, wh, p["id"], 6, "out")  # stock is gone → cannot return what is not there
    r = await ret(1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    async def pay(amount):
        return await o.client.post(
            f"{API}/purchases/{po['id']}/payments",
            headers=o.h,
            json={"amount": str(amount), "method": "bank_transfer"},
        )

    r = await pay("30.00")
    assert r.json()["data"]["paid_amount"] == "30.00" and r.json()["data"]["balance_due"] == "50.00"
    r = await pay("50.01")
    assert r.status_code == 409 and r.json()["error"]["code"] == "OVERPAYMENT"
    assert (await pay("50.00")).json()["data"]["balance_due"] == "0.00"
    assert (await pay("0")).status_code == 422


async def test_purchasing_isolation_permissions_and_branch_scope(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    a_wh, b_wh = await main_warehouse(a), await main_warehouse(b)
    a_p, b_p = await create_product(a), await create_product(b)
    b_sup = await supplier(b)
    b_po = await purchase(b, b_wh, [(b_p["id"], 5, 1)], sup=b_sup)

    await purchase(a, a_wh, [(a_p["id"], 1, 1)], sup=b_sup, expect=400)  # B's supplier
    await purchase(a, a_wh, [(b_p["id"], 1, 1)], expect=400)  # B's product
    await purchase(a, b_wh, [(a_p["id"], 1, 1)], expect=404)  # B's warehouse
    assert (await a.client.get(f"{API}/purchases/{b_po['id']}", headers=a.h)).status_code == 404
    assert (await receive(a, b_po["id"])).status_code == 404
    assert (await a.client.get(f"{API}/purchases", headers=a.h)).json()["data"]["total"] == 0
    assert (await b.client.get(f"{API}/suppliers", headers=b.h)).json()["data"][
        "total"
    ] == 1  # A created none in B
    assert await stock_of(b, b_p["id"]) in ("0", "0.000")

    # numbering is per company
    a_po = await purchase(a, a_wh, [(a_p["id"], 1, 1)])
    assert a_po["number"] == "PO-000001" == b_po["number"]

    cashier = await login(app, await add_member(a, "sales_cashier"))
    assert (await cashier.client.get(f"{API}/purchases", headers=cashier.h)).status_code == 403
    wh_emp = await login(app, await add_member(a, "warehouse_employee"))
    await purchase(wh_emp, a_wh, [(a_p["id"], 1, 1)], sup=a_po["supplier_id"], expect=403)
    assert (await receive(wh_emp, a_po["id"])).status_code == 200  # may receive, not order

    other_branch = (
        await a.client.post(f"{API}/branches", headers=a.h, json={"name": "B2", "code": "B2"})
    ).json()["data"]["id"]
    scoped = await login(
        app, await add_member(a, "purchase_manager", branch_ids=[uuid.UUID(other_branch)])
    )
    assert (
        await scoped.client.get(f"{API}/purchases/{a_po['id']}", headers=scoped.h)
    ).status_code == 404
    assert (await scoped.client.get(f"{API}/purchases", headers=scoped.h)).json()["data"][
        "total"
    ] == 0
    assert Decimal(await stock_of(a, a_p["id"])) == Decimal("1")
