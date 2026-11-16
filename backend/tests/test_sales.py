import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.db.tenant import context_transaction
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
from tests.test_purchasing import avg_cost, purchase, receive


async def stocked(o, wh, qty=10, cost="10.0000", **product):
    """A product whose stock (and average cost) came from a real purchase receipt."""
    p = await create_product(o, **product)
    po = await purchase(o, wh, [(p["id"], qty, cost)])
    await receive(o, po["id"])
    return p


async def customer(o, name="Mona Ali"):
    r = await o.client.post(f"{API}/customers", headers=o.h, json={"name": name})
    return r.json()["data"]["id"]


def body(wh, lines, pay=None, **extra):
    data = {
        "warehouse_id": wh,
        "items": [
            {"product_id": p, "quantity": str(q), **(rest[0] if rest else {})}
            for p, q, *rest in lines
        ],
        **extra,
    }
    if pay is not None:
        data["payments"] = [{"method": m, "amount": str(a)} for m, a in pay]
    return data


async def sell(o, wh, lines, pay=None, expect=201, headers=None, **extra):
    r = await o.client.post(
        f"{API}/sales", headers={**o.h, **(headers or {})}, json=body(wh, lines, pay, **extra)
    )
    assert r.status_code == expect, r.text
    return r.json()["data"] if expect == 201 else r.json()["error"]


async def movements(o, **params):
    r = await o.client.get(
        f"{API}/inventory/movements", headers=o.h, params={"page_size": 100, **params}
    )
    return r.json()["data"]["items"]


# ───────────────────────── posting ─────────────────────────


async def test_sale_totals_tax_cost_snapshot_and_stock(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p1 = await stocked(o, wh, 10, "60.0000", selling_price="100.00", tax_rate="14")
    p2 = await stocked(o, wh, 10, "5.0000", selling_price="9.99")

    sale = await sell(
        o,
        wh,
        [(p1["id"], 2, {"discount_amount": "10.00"}), (p2["id"], "1.500")],
        pay=[("cash", "250.00")],
    )
    # line 1: 200.00 − 10.00 = 190.00, tax 26.60 → 216.60 ; line 2: 1.5×9.99 = 14.985 → 14.99
    assert sale["number"] == "INV-000001"
    assert (sale["subtotal"], sale["discount_amount"], sale["tax_amount"], sale["total"]) == (
        "214.99",
        "10.00",
        "26.60",
        "231.59",
    )
    assert [i["line_total"] for i in sale["items"]] == ["216.60", "14.99"]
    assert sale["paid_amount"] == "231.59" and sale["change_due"] == "18.41"
    assert sale["payment_status"] == "paid" and sale["balance_due"] == "0.00"
    assert [p["amount"] for p in sale["payments"]] == ["231.59"]  # change is not booked as income
    assert await stock_of(o, p1["id"]) == "8.000" and await stock_of(o, p2["id"]) == "8.500"

    out = [m for m in await movements(o) if m["movement_type"] == "sale"]
    assert {(m["product_id"], m["quantity_out"], m["unit_cost"]) for m in out} == {
        (p1["id"], "2.000", "60.0000"),
        (p2["id"], "1.500", "5.0000"),
    }
    assert {m["reference_id"] for m in out} == {sale["id"]}

    # cost snapshot survives a later change of the average cost
    po = await purchase(o, wh, [(p1["id"], 8, "100.0000")])
    await receive(o, po["id"])
    assert await avg_cost(o, p1["id"]) == "80.0000"
    async with context_transaction(o.ctx) as s:
        costs = (
            (
                await s.execute(
                    text(
                        "SELECT unit_cost_at_sale FROM sale_items WHERE sale_id = :s ORDER BY line_no"
                    ),
                    {"s": sale["id"]},
                )
            )
            .scalars()
            .all()
        )
        cost_total = (
            await s.execute(text("SELECT cost_total FROM sales WHERE id = :s"), {"s": sale["id"]})
        ).scalar_one()
    assert costs == [Decimal("60.0000"), Decimal("5.0000")] and cost_total == Decimal("127.50")


async def test_client_cannot_dictate_totals_or_tenant(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, selling_price="50.00")
    for extra in (
        {"total": "1.00"},
        {"tenant_id": str(uuid.uuid4())},
        {"number": "INV-9"},
        {"paid_amount": "50"},
    ):
        await sell(o, wh, [(p["id"], 1)], pay=[("cash", 50)], expect=422, **extra)
    r = await o.client.post(
        f"{API}/sales",
        headers=o.h,
        json={
            "warehouse_id": wh,
            "payments": [{"method": "cash", "amount": "50"}],
            "items": [
                {
                    "product_id": p["id"],
                    "quantity": "1",
                    "line_total": "0.01",
                    "unit_cost_at_sale": "0",
                }
            ],
        },
    )
    assert r.status_code == 422
    for qty in ("0", "-1", "0.0001"):
        await sell(o, wh, [(p["id"], qty)], pay=[("cash", 50)], expect=422)
    err = await sell(
        o, wh, [(p["id"], 1, {"discount_amount": "50.01"})], pay=[("cash", 50)], expect=400
    )
    assert err["code"] == "DISCOUNT_TOO_LARGE"
    await sell(o, wh, [], expect=422)
    assert await stock_of(o, p["id"]) == "10.000"


async def test_overselling_is_rejected_and_nothing_is_written(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    plenty, scarce = await stocked(o, wh, 10), await stocked(o, wh, 2)
    before = len(await movements(o))
    err = await sell(
        o, wh, [(plenty["id"], 3), (scarce["id"], 3)], pay=[("cash", 1000)], expect=409
    )
    assert err["code"] == "INSUFFICIENT_STOCK" and err["details"]["available"] == "2.000"
    assert await stock_of(o, plenty["id"]) == "10.000" and len(await movements(o)) == before
    assert (await o.client.get(f"{API}/sales", headers=o.h)).json()["data"]["total"] == 0
    # the failed attempt did not consume an invoice number
    sale = await sell(o, wh, [(scarce["id"], 2)], pay=[("cash", 1000)])
    assert sale["number"] == "INV-000001"


async def test_concurrent_checkouts_never_oversell_and_numbers_are_unique(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 5, selling_price="10.00")

    async def checkout():
        return await new_client(app).post(
            f"{API}/sales", headers=o.h, json=body(wh, [(p["id"], 1)], [("cash", 10)])
        )

    results = await asyncio.gather(*[checkout() for _ in range(15)])
    assert sorted(r.status_code for r in results) == [201] * 5 + [409] * 10
    numbers = sorted(r.json()["data"]["number"] for r in results if r.status_code == 201)
    assert numbers == [f"INV-{n:06d}" for n in range(1, 6)]  # unique AND gap-free
    assert await stock_of(o, p["id"]) == "0.000"


async def test_checkout_retry_with_same_idempotency_key_creates_one_invoice(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 10, selling_price="10.00")
    key = {"Idempotency-Key": f"pos-{uuid.uuid4()}"}
    payload = body(wh, [(p["id"], 2)], [("cash", 20)])
    results = await asyncio.gather(
        *[
            new_client(app).post(f"{API}/sales", headers={**o.h, **key}, json=payload)
            for _ in range(6)
        ]
    )
    assert {r.status_code for r in results} == {201}
    assert len({r.json()["data"]["id"] for r in results}) == 1
    assert await stock_of(o, p["id"]) == "8.000"
    assert (await o.client.get(f"{API}/sales", headers=o.h)).json()["data"]["total"] == 1
    async with context_transaction(o.ctx) as s:
        assert (
            await s.execute(
                text("SELECT count(*), sum(amount) FROM payments WHERE direction = 'in'")
            )
        ).one() == (1, Decimal("20.00"))


# ───────────────────────── payments ─────────────────────────


async def test_credit_sale_requires_customer_and_tracks_balance(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, selling_price="100.00")
    err = await sell(o, wh, [(p["id"], 1)], pay=[("cash", 40)], expect=400)
    assert err["code"] == "CUSTOMER_REQUIRED"
    assert await stock_of(o, p["id"]) == "10.000"

    cust = await customer(o)
    sale = await sell(o, wh, [(p["id"], 1)], pay=[("cash", 40)], customer_id=cust)
    assert (sale["payment_status"], sale["balance_due"], sale["customer_name"]) == (
        "partial",
        "60.00",
        "Mona Ali",
    )
    unpaid = (await o.client.get(f"{API}/sales", headers=o.h, params={"unpaid_only": True})).json()[
        "data"
    ]
    assert [s["id"] for s in unpaid["items"]] == [sale["id"]]

    async def pay(amount, method="card"):
        return await o.client.post(
            f"{API}/sales/{sale['id']}/payments",
            headers=o.h,
            json={"amount": str(amount), "method": method},
        )

    r = await pay("60.01")
    assert r.status_code == 409 and r.json()["error"]["code"] == "OVERPAYMENT"
    assert (await pay("10.00")).json()["data"]["balance_due"] == "50.00"
    done = (await pay("50.00", "bank_transfer")).json()["data"]
    assert done["payment_status"] == "paid" and [p["method"] for p in done["payments"]] == [
        "cash",
        "card",
        "bank_transfer",
    ]
    assert (await pay("0.01")).status_code == 409

    # split payment, non-cash overpayment is refused
    err = await sell(o, wh, [(p["id"], 1)], pay=[("card", 150)], expect=400)
    assert err["code"] == "OVERPAYMENT"
    split = await sell(o, wh, [(p["id"], 1)], pay=[("card", 70), ("cash", 50)])
    assert sorted((x["method"], x["amount"]) for x in split["payments"]) == [
        ("card", "70.00"),
        ("cash", "30.00"),
    ]
    assert split["change_due"] == "20.00"


# ───────────────────────── returns & cancellation ─────────────────────────


async def test_partial_returns_restock_refund_and_never_exceed_the_sale(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 10, "4.0000", selling_price="10.00", tax_rate="14")
    sale = await sell(o, wh, [(p["id"], 3)], pay=[("cash", "34.20")])  # 30 + 4.20
    item = sale["items"][0]["id"]

    async def ret(q, **headers):
        return await o.client.post(
            f"{API}/sales/{sale['id']}/returns",
            headers={**o.h, **headers},
            json={
                "items": [{"sale_item_id": item, "quantity": str(q)}],
                "reason": "customer changed mind",
            },
        )

    key = {"Idempotency-Key": f"ret-{uuid.uuid4()}"}
    first = (await ret(1, **key)).json()["data"]
    assert (await ret(1, **key)).json()["data"][
        "idempotent_replay"
    ] is True  # retried, not repeated
    assert first["refund_amount"] == "11.40" and first["returned_amount"] == "11.40"
    assert first["paid_amount"] == "22.80" and first["items"][0]["returned_quantity"] == "1.000"
    assert await stock_of(o, p["id"]) == "8.000"

    r = await ret(3)
    assert r.status_code == 409 and r.json()["error"]["code"] == "OVER_RETURN"
    rest = (await ret(2)).json()["data"]
    assert (
        rest["returned_amount"] == "34.20" and rest["paid_amount"] == "0.00"
    )  # exact, no cent lost
    assert await stock_of(o, p["id"]) == "10.000"
    assert (await ret(1)).status_code == 409
    assert await avg_cost(o, p["id"]) == "4.0000"

    back = [
        m for m in await movements(o, product_id=p["id"]) if m["movement_type"] == "sale_return"
    ]
    assert sorted(m["quantity_in"] for m in back) == ["1.000", "2.000"] and {
        m["unit_cost"] for m in back
    } == {"4.0000"}
    r = await o.client.post(
        f"{API}/sales/{sale['id']}/cancel", headers=o.h, json={"reason": "void it"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_RETURNS"


async def test_return_on_credit_sale_reduces_debt_before_refunding(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, selling_price="100.00")
    sale = await sell(
        o, wh, [(p["id"], 4)], pay=[("cash", 100)], customer_id=await customer(o)
    )  # owes 300
    r = await o.client.post(
        f"{API}/sales/{sale['id']}/returns",
        headers=o.h,
        json={
            "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "2"}],
            "reason": "defective",
        },
    )
    data = r.json()["data"]
    assert (
        data["refund_amount"] == "0.00"
        and data["paid_amount"] == "100.00"
        and data["balance_due"] == "100.00"
    )
    r = await o.client.post(
        f"{API}/sales/{sale['id']}/returns",
        headers=o.h,
        json={
            "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "2"}],
            "reason": "defective",
        },
    )
    data = r.json()["data"]
    assert (
        data["refund_amount"] == "100.00"
        and data["paid_amount"] == "0.00"
        and data["balance_due"] == "0.00"
    )


async def test_cancel_restores_stock_and_refunds(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 10, selling_price="10.00")
    sale = await sell(o, wh, [(p["id"], 4)], pay=[("cash", 40)])
    r = await o.client.post(
        f"{API}/sales/{sale['id']}/cancel", headers=o.h, json={"reason": "wrong customer"}
    )
    data = r.json()["data"]
    assert (
        r.status_code == 200 and data["status"] == "cancelled" and data["refund_amount"] == "40.00"
    )
    assert data["paid_amount"] == "0.00" and data["payment_status"] == "cancelled"
    assert await stock_of(o, p["id"]) == "10.000"
    again = await o.client.post(
        f"{API}/sales/{sale['id']}/cancel", headers=o.h, json={"reason": "wrong customer"}
    )
    assert again.status_code == 409 and await stock_of(o, p["id"]) == "10.000"
    for path, payload in (
        (
            "returns",
            {"items": [{"sale_item_id": sale["items"][0]["id"], "quantity": "1"}], "reason": "xxx"},
        ),
        ("payments", {"amount": "1"}),
    ):
        assert (
            await o.client.post(f"{API}/sales/{sale['id']}/{path}", headers=o.h, json=payload)
        ).status_code == 409
    logs = (
        await o.client.get(f"{API}/audit-logs", headers=o.h, params={"entity_type": "sale"})
    ).json()["data"]["items"]
    assert [log["action"] for log in logs] == ["sale.cancelled", "sale.created"]
    assert logs[0]["data"]["reason"] == "wrong customer" and logs[0]["user_name"]


async def test_posted_documents_are_protected_at_database_level(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, selling_price="10.00")
    await sell(o, wh, [(p["id"], 1)], pay=[("cash", 10)])
    for statement in (
        "DELETE FROM sales",
        "DELETE FROM sale_items",
        "UPDATE payments SET amount = 1",
        "DELETE FROM payments",
        "UPDATE audit_logs SET action = 'x'",
        "DELETE FROM audit_logs",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with context_transaction(o.ctx) as s:
                await s.execute(text(statement))


# ───────────────────────── isolation, permissions, misc ─────────────────────────


async def test_sales_isolation_between_companies(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    a_wh, b_wh = await main_warehouse(a), await main_warehouse(b)
    a_p, b_p = await stocked(a, a_wh), await stocked(b, b_wh)
    b_cust = await customer(b)
    b_sale = await sell(b, b_wh, [(b_p["id"], 1)], pay=[("cash", 100)])

    assert (await sell(a, a_wh, [(b_p["id"], 1)], pay=[("cash", 100)], expect=400))[
        "code"
    ] == "INVALID_REFERENCE"
    await sell(a, b_wh, [(a_p["id"], 1)], pay=[("cash", 100)], expect=404)
    await sell(a, a_wh, [(a_p["id"], 1)], pay=[("cash", 100)], expect=400, customer_id=b_cust)
    for method, path, payload in (
        ("get", "", None),
        ("post", "/cancel", {"reason": "hack"}),
        ("post", "/payments", {"amount": "1"}),
        (
            "post",
            "/returns",
            {
                "items": [{"sale_item_id": b_sale["items"][0]["id"], "quantity": "1"}],
                "reason": "hack",
            },
        ),
    ):
        r = await a.client.request(
            method, f"{API}/sales/{b_sale['id']}{path}", headers=a.h, json=payload
        )
        assert r.status_code == 404, path
    assert (await a.client.get(f"{API}/sales", headers=a.h)).json()["data"]["total"] == 0
    assert (await a.client.get(f"{API}/customers", headers=a.h)).json()["data"]["total"] == 0
    assert await stock_of(b, b_p["id"]) == "9.000" and await stock_of(a, a_p["id"]) == "10.000"
    a_sale = await sell(a, a_wh, [(a_p["id"], 1)], pay=[("cash", 100)])
    assert a_sale["number"] == b_sale["number"] == "INV-000001"  # numbering is per company


async def test_sales_permissions_and_branch_scope(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, selling_price="10.00")
    sale = await sell(o, wh, [(p["id"], 1)], pay=[("cash", 10)])

    cashier = await login(app, await add_member(o, "sales_cashier"))
    mine = await sell(cashier, wh, [(p["id"], 1)], pay=[("cash", 10)])
    r = await cashier.client.post(
        f"{API}/sales/{mine['id']}/cancel", headers=cashier.h, json={"reason": "nope"}
    )
    assert r.status_code == 403  # cashiers cannot void invoices
    assert (await cashier.client.get(f"{API}/audit-logs", headers=cashier.h)).status_code == 403
    wh_emp = await login(app, await add_member(o, "warehouse_employee"))
    assert (await wh_emp.client.get(f"{API}/sales", headers=wh_emp.h)).status_code == 403
    await sell(wh_emp, wh, [(p["id"], 1)], pay=[("cash", 10)], expect=403)

    other = (
        await o.client.post(f"{API}/branches", headers=o.h, json={"name": "B2", "code": "B2"})
    ).json()["data"]["id"]
    scoped = await login(app, await add_member(o, "sales_cashier", branch_ids=[uuid.UUID(other)]))
    assert (
        await scoped.client.get(f"{API}/sales/{sale['id']}", headers=scoped.h)
    ).status_code == 404
    assert (await scoped.client.get(f"{API}/sales", headers=scoped.h)).json()["data"]["total"] == 0
    await sell(scoped, wh, [(p["id"], 1)], pay=[("cash", 10)], expect=404)


async def test_untracked_and_inactive_products(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    service = await create_product(o, name="Delivery", track_inventory=False, selling_price="25.00")
    sale = await sell(o, wh, [(service["id"], 2)], pay=[("cash", 50)])
    assert sale["total"] == "50.00" and await movements(o, product_id=service["id"]) == []
    await o.client.patch(f"{API}/products/{service['id']}", headers=o.h, json={"is_active": False})
    assert (await sell(o, wh, [(service["id"], 1)], pay=[("cash", 25)], expect=400))[
        "code"
    ] == "INACTIVE_REFERENCE"


async def test_low_stock_notification_is_raised_once_and_can_be_read(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 10, selling_price="10.00", name="Lamp")
    await o.client.put(
        f"{API}/inventory/minimum-level",
        headers=o.h,
        json={"warehouse_id": wh, "product_id": p["id"], "minimum_stock_level": "5"},
    )
    await sell(o, wh, [(p["id"], 2)], pay=[("cash", 20)])
    assert (await o.client.get(f"{API}/notifications", headers=o.h)).json()["data"]["unread"] == 0
    await sell(o, wh, [(p["id"], 3)], pay=[("cash", 30)])  # 5 left → at the minimum
    await sell(o, wh, [(p["id"], 1)], pay=[("cash", 10)])  # still low → no second notification
    data = (await o.client.get(f"{API}/notifications", headers=o.h)).json()["data"]
    assert (
        data["unread"] == 1
        and data["items"][0]["type"] == "low_stock"
        and data["items"][0]["title"] == "Lamp"
    )

    accountant = await login(app, await add_member(o, "accountant"))  # no inventory.view
    assert (await accountant.client.get(f"{API}/notifications", headers=accountant.h)).json()[
        "data"
    ]["total"] == 0
    other = await register_company(app, "Other Co")
    assert (await other.client.get(f"{API}/notifications", headers=other.h)).json()["data"][
        "total"
    ] == 0

    await o.client.post(f"{API}/notifications/{data['items'][0]['id']}/read", headers=o.h)
    assert (await o.client.get(f"{API}/notifications", headers=o.h)).json()["data"]["unread"] == 0
    await sell(o, wh, [(p["id"], 1)], pay=[("cash", 10)])  # read → a new alert may be raised
    assert (await o.client.get(f"{API}/notifications", headers=o.h)).json()["data"]["unread"] == 1
    _ = adjust
