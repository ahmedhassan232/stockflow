import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

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


async def _second_warehouse(o, code="W2", branch_id=None):
    body = {"name": f"Warehouse {code}", "code": code}
    if branch_id:
        body["branch_id"] = branch_id
    r = await o.client.post(f"{API}/warehouses", headers=o.h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def _transfer(o, src, dst, items, **headers):
    return await o.client.post(
        f"{API}/inventory/transfers",
        headers={**o.h, **headers},
        json={
            "from_warehouse_id": src,
            "to_warehouse_id": dst,
            "items": [{"product_id": p, "quantity": str(q)} for p, q in items],
        },
    )


async def _movements(o, **params):
    r = await o.client.get(
        f"{API}/inventory/movements", headers=o.h, params={"page_size": 100, **params}
    )
    return r.json()["data"]["items"]


async def _ledger_matches_balances(o):
    """Invariant: every balance equals the sum of its ledger rows."""
    async with context_transaction(o.ctx) as s:
        rows = await s.execute(
            text(
                "SELECT b.quantity, COALESCE(SUM(m.quantity_in - m.quantity_out), 0) "
                "FROM stock_balances b LEFT JOIN inventory_movements m "
                "  ON m.warehouse_id = b.warehouse_id AND m.product_id = b.product_id "
                "GROUP BY b.id, b.quantity"
            )
        )
        for quantity, ledger in rows.all():
            assert quantity == ledger


# ───────────────────────── adjustments ─────────────────────────


async def test_adjustment_changes_balance_and_writes_ledger(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    r = await adjust(o, wh, p["id"], "10.500")
    assert r.status_code == 201 and r.json()["data"]["balance_after"] == "10.500"
    r = await adjust(o, wh, p["id"], "4", "out")
    assert r.json()["data"]["balance_after"] == "6.500"
    assert await stock_of(o, p["id"]) == "6.500"

    moves = await _movements(o, product_id=p["id"])
    assert [
        (m["movement_type"], m["quantity_in"], m["quantity_out"], m["balance_after"]) for m in moves
    ] == [
        ("adjustment_out", "0.000", "4.000", "6.500"),
        ("adjustment_in", "10.500", "0.000", "10.500"),
    ]
    assert all(
        m["created_by"] == str(o.user_id) and m["reference_type"] == "stock_adjustment"
        for m in moves
    )
    await _ledger_matches_balances(o)


async def test_adjustment_out_beyond_stock_is_rejected_and_changes_nothing(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    await adjust(o, wh, p["id"], 5)
    r = await adjust(o, wh, p["id"], 6, "out")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "INSUFFICIENT_STOCK"
    assert err["details"]["available"] == "5.000" and err["details"]["requested"] == "6"
    assert await stock_of(o, p["id"]) == "5.000"
    assert len(await _movements(o, product_id=p["id"])) == 1


async def test_adjustment_validation(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    for qty in ("0", "-1", "1.0001"):
        assert (await adjust(o, wh, p["id"], qty)).status_code == 422
    r = await o.client.post(
        f"{API}/inventory/adjustments",
        headers=o.h,
        json={
            "warehouse_id": wh,
            "product_id": p["id"],
            "direction": "in",
            "quantity": "1",
            "reason": "",
        },
    )
    assert r.status_code == 422  # a reason is mandatory
    assert (await adjust(o, uuid.uuid4(), p["id"], 1)).status_code == 404
    assert (await adjust(o, wh, uuid.uuid4(), 1)).status_code == 400
    untracked = await create_product(o, track_inventory=False)
    assert (await adjust(o, wh, untracked["id"], 1)).json()["error"]["code"] == "NOT_TRACKED"


async def test_negative_stock_only_when_company_setting_allows_it(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    assert (await adjust(o, wh, p["id"], 1, "out")).status_code == 409
    async with context_transaction(o.ctx) as s:
        await s.execute(text("UPDATE company_settings SET allow_negative_stock = true"))
    r = await adjust(o, wh, p["id"], 1, "out")
    assert r.status_code == 201 and r.json()["data"]["balance_after"] == "-1.000"


# ───────────────────────── transfers ─────────────────────────


async def test_transfer_moves_stock_between_warehouses(app):
    o = await register_company(app)
    src, dst = await main_warehouse(o), await _second_warehouse(o)
    p = await create_product(o)
    await adjust(o, src, p["id"], 10)
    r = await _transfer(o, src, dst, [(p["id"], 4)])
    assert r.status_code == 201, r.text
    assert await stock_of(o, p["id"], src) == "6.000"
    assert await stock_of(o, p["id"], dst) == "4.000"
    pair = [
        m
        for m in await _movements(o, product_id=p["id"])
        if m["reference_type"] == "stock_transfer"
    ]
    assert {(m["movement_type"], m["warehouse_id"]) for m in pair} == {
        ("transfer_out", src),
        ("transfer_in", dst),
    }
    assert len({m["reference_id"] for m in pair}) == 1
    await _ledger_matches_balances(o)


async def test_failed_transfer_leaves_no_partial_update(app):
    o = await register_company(app)
    src, dst = await main_warehouse(o), await _second_warehouse(o)
    plenty, scarce = await create_product(o), await create_product(o)
    await adjust(o, src, plenty["id"], 10)
    await adjust(o, src, scarce["id"], 1)
    before = len(await _movements(o))

    r = await _transfer(o, src, dst, [(plenty["id"], 5), (scarce["id"], 2)])  # 2nd line fails
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert await stock_of(o, plenty["id"], src) == "10.000"  # 1st line was rolled back
    assert await stock_of(o, plenty["id"], dst) in ("0", "0.000")
    assert len(await _movements(o)) == before
    async with context_transaction(o.ctx) as s:
        assert (await s.execute(text("SELECT count(*) FROM stock_transfers"))).scalar_one() == 0


async def test_transfer_validation(app):
    o = await register_company(app)
    src, dst = await main_warehouse(o), await _second_warehouse(o)
    p = await create_product(o)
    assert (await _transfer(o, src, src, [(p["id"], 1)])).status_code == 422
    assert (await _transfer(o, src, dst, [(p["id"], 1), (p["id"], 1)])).status_code == 422
    assert (await _transfer(o, src, dst, [])).status_code == 422
    assert (await _transfer(o, src, str(uuid.uuid4()), [(p["id"], 1)])).status_code == 404


# ───────────────────────── idempotency ─────────────────────────


async def test_duplicate_requests_do_not_duplicate_movements(app):
    o = await register_company(app)
    src, dst = await main_warehouse(o), await _second_warehouse(o)
    p = await create_product(o)
    key = {"Idempotency-Key": f"adj-{uuid.uuid4()}"}
    first = await adjust(o, src, p["id"], 10, headers=key)
    second = await adjust(o, src, p["id"], 10, headers=key)
    assert first.status_code == second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert second.json()["data"]["idempotent_replay"] is True
    assert await stock_of(o, p["id"]) == "10.000"

    different = await adjust(o, src, p["id"], 99, headers=key)
    assert (
        different.status_code == 409
        and different.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    )

    tkey = {"Idempotency-Key": f"trf-{uuid.uuid4()}"}
    results = await asyncio.gather(
        *[
            new_client(app).post(
                f"{API}/inventory/transfers",
                headers={**o.h, **tkey},
                json={
                    "from_warehouse_id": src,
                    "to_warehouse_id": dst,
                    "items": [{"product_id": p["id"], "quantity": "3"}],
                },
            )
            for _ in range(5)
        ]
    )
    assert {r.status_code for r in results} == {201}
    assert len({r.json()["data"]["id"] for r in results}) == 1  # executed exactly once
    assert await stock_of(o, p["id"], src) == "7.000" and await stock_of(o, p["id"], dst) == "3.000"


async def test_failed_request_does_not_burn_the_idempotency_key(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    key = {"Idempotency-Key": f"k-{uuid.uuid4()}"}
    assert (await adjust(o, wh, p["id"], 5, "out", headers=key)).status_code == 409
    await adjust(o, wh, p["id"], 10)
    assert (await adjust(o, wh, p["id"], 5, "out", headers=key)).status_code == 201


async def test_idempotency_keys_are_scoped_per_company(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    key = {"Idempotency-Key": "same-key-in-both-companies"}
    for acc in (a, b):
        r = await adjust(
            acc, await main_warehouse(acc), (await create_product(acc))["id"], 2, headers=key
        )
        assert r.status_code == 201 and r.json()["data"]["idempotent_replay"] is False


# ───────────────────────── concurrency ─────────────────────────


async def test_concurrent_withdrawals_never_oversell(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    await adjust(o, wh, p["id"], 10)

    async def take():
        return await new_client(app).post(
            f"{API}/inventory/adjustments",
            headers=o.h,
            json={
                "warehouse_id": wh,
                "product_id": p["id"],
                "direction": "out",
                "quantity": "3",
                "reason": "concurrent",
            },
        )

    codes = sorted(r.status_code for r in await asyncio.gather(*[take() for _ in range(12)]))
    assert codes == [201] * 3 + [409] * 9  # 3 × 3 = 9 ≤ 10; a 4th would oversell
    assert await stock_of(o, p["id"]) == "1.000"
    await _ledger_matches_balances(o)


async def test_opposite_concurrent_transfers_do_not_deadlock_and_conserve_stock(app):
    o = await register_company(app)
    w1, w2 = await main_warehouse(o), await _second_warehouse(o)
    p1, p2 = await create_product(o), await create_product(o)
    for w in (w1, w2):
        for p in (p1, p2):
            await adjust(o, w, p["id"], 100)

    async def go(src, dst, items):
        return await new_client(app).post(
            f"{API}/inventory/transfers",
            headers=o.h,
            json={
                "from_warehouse_id": src,
                "to_warehouse_id": dst,
                "items": [{"product_id": p["id"], "quantity": "1"} for p in items],
            },
        )

    jobs = []
    for _ in range(10):  # opposite directions AND opposite line order
        jobs += [go(w1, w2, [p1, p2]), go(w2, w1, [p2, p1])]
    results = await asyncio.gather(*jobs)
    assert {r.status_code for r in results} == {201}
    for p in (p1, p2):
        total = Decimal(await stock_of(o, p["id"], w1)) + Decimal(await stock_of(o, p["id"], w2))
        assert total == Decimal("200")
    await _ledger_matches_balances(o)


# ───────────────────────── ledger integrity ─────────────────────────


async def test_ledger_is_append_only_and_duplicates_are_blocked_by_the_database(app):
    o = await register_company(app)
    wh, p = await main_warehouse(o), await create_product(o)
    await adjust(o, wh, p["id"], 5)
    for statement in (
        "UPDATE inventory_movements SET quantity_in = 999",
        "DELETE FROM inventory_movements",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with context_transaction(o.ctx) as s:
                await s.execute(text(statement))
    with pytest.raises(IntegrityError, match="uq_inventory_movements_reference"):
        async with context_transaction(o.ctx) as s:
            await s.execute(
                text(
                    "INSERT INTO inventory_movements (tenant_id, product_id, warehouse_id, movement_type,"
                    " quantity_in, balance_after, reference_type, reference_id, line_no, created_by) "
                    "SELECT tenant_id, product_id, warehouse_id, movement_type, quantity_in, balance_after,"
                    " reference_type, reference_id, line_no, created_by FROM inventory_movements"
                )
            )
    with pytest.raises(IntegrityError, match="exactly_one_direction"):
        async with context_transaction(o.ctx) as s:
            await s.execute(
                text(
                    "INSERT INTO inventory_movements (tenant_id, product_id, warehouse_id, movement_type,"
                    " quantity_in, quantity_out, balance_after, reference_type, reference_id, created_by) "
                    "SELECT tenant_id, product_id, warehouse_id, 'adjustment_in', 1, 1, 0, 'x',"
                    " gen_random_uuid(), created_by FROM inventory_movements"
                )
            )


# ───────────────────────── isolation & permissions ─────────────────────────


async def test_inventory_is_isolated_between_companies(app):
    a, b = await register_company(app, "Alpha Co"), await register_company(app, "Beta Co")
    a_wh, b_wh = await main_warehouse(a), await main_warehouse(b)
    a_p, b_p = await create_product(a), await create_product(b)
    await adjust(b, b_wh, b_p["id"], 50)

    assert (await adjust(a, b_wh, a_p["id"], 1)).status_code == 404  # B's warehouse
    assert (await adjust(a, a_wh, b_p["id"], 1)).status_code == 400  # B's product
    assert (await _transfer(a, a_wh, b_wh, [(a_p["id"], 1)])).status_code == 404
    listing = (await a.client.get(f"{API}/inventory", headers=a.h)).json()["data"]
    assert listing["total"] == 0
    assert await _movements(a) == []
    assert await _movements(a, product_id=b_p["id"]) == []
    assert await stock_of(b, b_p["id"]) == "50.000"


async def test_inventory_permissions_and_branch_scope(app):
    o = await register_company(app)
    main_wh, p = await main_warehouse(o), await create_product(o)
    main_branch = (await o.client.get(f"{API}/branches", headers=o.h)).json()["data"]["items"][0][
        "id"
    ]
    other_branch = (
        await o.client.post(f"{API}/branches", headers=o.h, json={"name": "B2", "code": "B2"})
    ).json()["data"]["id"]
    other_wh = await _second_warehouse(o, "W2", other_branch)
    await adjust(o, main_wh, p["id"], 10)
    await adjust(o, other_wh, p["id"], 20)

    wh_emp = await login(app, await add_member(o, "warehouse_employee"))
    assert (
        await adjust(wh_emp, main_wh, p["id"], 1)
    ).status_code == 403  # may transfer, not adjust
    assert (await _transfer(wh_emp, main_wh, other_wh, [(p["id"], 1)])).status_code == 201
    accountant = await login(app, await add_member(o, "accountant"))
    assert (
        await accountant.client.get(f"{API}/inventory", headers=accountant.h)
    ).status_code == 403

    scoped = await login(
        app, await add_member(o, "inventory_manager", branch_ids=[uuid.UUID(main_branch)])
    )
    seen = (await scoped.client.get(f"{API}/inventory", headers=scoped.h)).json()["data"]["items"]
    assert {i["warehouse_id"] for i in seen} == {main_wh}
    assert {m["warehouse_id"] for m in await _movements(scoped)} == {main_wh}
    assert (await adjust(scoped, other_wh, p["id"], 1)).status_code == 404
    assert (await _transfer(scoped, main_wh, other_wh, [(p["id"], 1)])).status_code == 404
    assert (await adjust(scoped, main_wh, p["id"], 1)).status_code == 201
    detail = (await scoped.client.get(f"{API}/products/{p['id']}", headers=scoped.h)).json()["data"]
    assert [s["warehouse_id"] for s in detail["stock"]] == [main_wh]


# ───────────────────────── low stock & valuation ─────────────────────────


async def test_low_stock_and_valuation_reports(app):
    o = await register_company(app)
    wh = await main_warehouse(o)
    low, fine = await create_product(o, name="Low"), await create_product(o, name="Fine")
    await adjust(o, wh, low["id"], 3)
    await adjust(o, wh, fine["id"], 50)
    for prod, level in ((low, "5"), (fine, "5")):
        r = await o.client.put(
            f"{API}/inventory/minimum-level",
            headers=o.h,
            json={"warehouse_id": wh, "product_id": prod["id"], "minimum_stock_level": level},
        )
        assert r.status_code == 200
    items = (await o.client.get(f"{API}/inventory/low-stock", headers=o.h)).json()["data"]["items"]
    assert [i["product_name"] for i in items] == ["Low"] and items[0]["is_low"] is True

    async with context_transaction(o.ctx) as s:  # costs normally come from purchase receipts
        await s.execute(
            text("UPDATE products SET average_cost = 2.5 WHERE id = :i"), {"i": low["id"]}
        )
        await s.execute(
            text("UPDATE products SET average_cost = 10 WHERE id = :i"), {"i": fine["id"]}
        )
    v = (await o.client.get(f"{API}/inventory/valuation", headers=o.h)).json()["data"]
    assert v["method"] == "weighted_average" and v["total_value"] == "507.50"  # 3×2.5 + 50×10
