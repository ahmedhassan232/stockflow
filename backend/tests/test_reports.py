from tests.api_helpers import API, add_member, login, main_warehouse, register_company
from tests.test_sales import customer, sell, stocked


async def test_sales_and_profit_reports_use_cost_snapshot_and_returns(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p1 = await stocked(o, wh, 20, "60.0000", selling_price="100.00", tax_rate="14", name="Blender")
    p2 = await stocked(o, wh, 20, "5.0000", selling_price="10.00", name="Cup")
    cust = await customer(o)

    s1 = await sell(o, wh, [(p1["id"], 2), (p2["id"], 4)], pay=[("cash", 300)])  # 228 + 40 = 268
    await sell(
        o, wh, [(p1["id"], 1, {"discount_amount": "10"})], pay=[("card", 50)], customer_id=cust
    )  # 90+12.6
    void = await sell(o, wh, [(p2["id"], 5)], pay=[("cash", 50)])
    await o.client.post(f"{API}/sales/{void['id']}/cancel", headers=o.h, json={"reason": "mistake"})
    await o.client.post(
        f"{API}/sales/{s1['id']}/returns",
        headers=o.h,
        json={
            "items": [{"sale_item_id": s1["items"][0]["id"], "quantity": "1"}],
            "reason": "faulty",
        },
    )

    profit = (await o.client.get(f"{API}/reports/profit", headers=o.h)).json()["data"]
    s = profit["summary"]
    assert s["invoice_count"] == 2  # cancelled invoice excluded
    assert (
        s["gross_sales"] == "370.60" and s["tax_collected"] == "40.60" and s["discounts"] == "10.00"
    )
    assert s["returns"] == "114.00"
    # revenue: (200+40) + 90 − 100 returned = 230 ; cogs: (120+20) + 60 − 60 = 140
    assert (s["revenue"], s["cogs"], s["gross_profit"], s["margin_percent"]) == (
        "230.00",
        "140.00",
        "90.00",
        "39.13",
    )
    assert (
        sum(float(d["revenue"]) for d in profit["by_day"]) == 230.0 and len(profit["by_day"]) == 30
    )
    top = {t["name"]: t for t in profit["top_products"]}
    assert (
        top["Blender"]["quantity"],
        top["Blender"]["revenue"],
        top["Blender"]["gross_profit"],
    ) == ("2.000", "190.00", "70.00")
    assert (top["Cup"]["quantity"], top["Cup"]["revenue"]) == ("4.000", "40.00")
    assert (
        profit["receivables"]["total"] == "52.60"
        and profit["receivables"]["customers"][0]["name"] == "Mona Ali"
    )

    sales = (await o.client.get(f"{API}/reports/sales", headers=o.h)).json()["data"]
    assert "gross_profit" not in sales["summary"] and "cogs" not in sales["by_day"][0]
    methods = {m["method"]: m for m in sales["by_payment_method"]}
    assert methods["cash"]["received"] == "318.00" and methods["cash"]["refunded"] == "164.00"
    assert methods["card"]["net"] == "50.00"
    assert sales["by_cashier"][0]["invoice_count"] == 2

    r = await o.client.get(
        f"{API}/reports/sales",
        headers=o.h,
        params={"date_from": "2026-02-01", "date_to": "2026-01-01"},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_RANGE"
    old = (
        await o.client.get(
            f"{API}/reports/sales",
            headers=o.h,
            params={"date_from": "2020-01-01", "date_to": "2020-01-31"},
        )
    ).json()["data"]
    assert old["summary"]["invoice_count"] == 0 and old["summary"]["gross_sales"] == "0.00"


async def test_dashboard_sections_follow_permissions_and_tenant(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    p = await stocked(o, wh, 10, "4.0000", selling_price="10.00")
    await sell(o, wh, [(p["id"], 2)], pay=[("cash", 20)])

    d = (await o.client.get(f"{API}/reports/dashboard", headers=o.h)).json()["data"]
    assert d["currency"] == "EGP" and d["sales_today"]["invoice_count"] == 1
    assert (
        d["sales_today"]["gross_sales"] == "20.00" and d["sales_month"]["gross_profit"] == "12.00"
    )
    assert d["inventory"] == {"stock_value": "32.00", "low_stock_count": 0, "active_products": 1}
    assert len(d["sales_by_day"]) == 14 and d["sales_by_day"][-1]["gross_sales"] == "20.00"
    assert d["top_products"][0]["quantity"] == "2.000"

    cashier = await login(app, await add_member(o, "sales_cashier"))
    c = (await cashier.client.get(f"{API}/reports/dashboard", headers=cashier.h)).json()["data"]
    assert c["sales_today"] is None and c["payables_total"] is None and c["top_products"] is None
    assert c["inventory"]["stock_value"] is None and c["inventory"]["active_products"] == 1
    assert (await cashier.client.get(f"{API}/reports/sales", headers=cashier.h)).status_code == 403
    assert (await cashier.client.get(f"{API}/reports/profit", headers=cashier.h)).status_code == 403

    manager = await login(app, await add_member(o, "branch_manager"))  # sales reports, no financial
    m = (await manager.client.get(f"{API}/reports/dashboard", headers=manager.h)).json()["data"]
    assert m["sales_today"]["gross_sales"] == "20.00" and "gross_profit" not in m["sales_today"]
    assert "gross_profit" not in m["top_products"][0] and "cogs" not in m["sales_by_day"][0]
    assert (await manager.client.get(f"{API}/reports/profit", headers=manager.h)).status_code == 403

    other = await register_company(app, "Other Co")
    x = (await other.client.get(f"{API}/reports/dashboard", headers=other.h)).json()["data"]
    assert x["sales_today"]["invoice_count"] == 0 and x["inventory"]["active_products"] == 0
    assert (await other.client.get(f"{API}/reports/profit", headers=other.h)).json()["data"][
        "summary"
    ]["revenue"] == "0.00"
