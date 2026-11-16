"""Phase 10: scheduled low-stock scan."""

from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.tasks.celery_app import celery_app
from app.tasks.low_stock import scan_low_stock
from tests.api_helpers import adjust, create_product, main_warehouse, register_company


async def _low_notifications(account) -> list[dict]:
    r = await account.client.get("/api/v1/notifications", headers=account.h)
    return [n for n in r.json()["data"]["items"] if n["type"] == "low_stock"]


async def test_scan_notifies_each_company_only_about_its_own_stock(app):
    a = await register_company(app, "Scan Alpha")
    b = await register_company(app, "Scan Beta")
    wa, wb = await main_warehouse(a), await main_warehouse(b)
    pa = await create_product(a, name="Alpha Tea")
    pb = await create_product(b, name="Beta Rice")
    for acc, w, p, qty in ((a, wa, pa, "3"), (b, wb, pb, "50")):
        await adjust(acc, w, p["id"], qty)
        r = await acc.client.put(
            "/api/v1/inventory/minimum-level",
            headers=acc.h,
            json={"warehouse_id": w, "product_id": p["id"], "minimum_stock_level": "5"},
        )
        assert r.status_code == 200, r.text

    result = await scan_low_stock(get_sessionmaker())
    assert result["failed"] == 0 and result["companies"] >= 2

    mine = await _low_notifications(a)
    assert [n["title"] for n in mine] == ["Alpha Tea"]
    assert mine[0]["data"]["quantity"] == "3.000"
    assert await _low_notifications(b) == []  # 50 > 5, and nothing leaked from Alpha

    await scan_low_stock(get_sessionmaker())  # idempotent: no duplicate while unread
    assert len(await _low_notifications(a)) == 1


async def test_worker_role_gets_ids_only_and_no_rows_without_tenant_context(app):
    await register_company(app, "Scan Gamma")
    async with get_sessionmaker()() as s, s.begin():
        ids = (await s.execute(text("SELECT app_active_tenant_ids()"))).scalars().all()
        assert len(ids) >= 1
        # without a tenant context RLS still hides every business row from the worker
        assert (await s.execute(text("SELECT count(*) FROM stock_balances"))).scalar() == 0
        assert (await s.execute(text("SELECT count(*) FROM tenants"))).scalar() == 0


def test_scan_is_scheduled():
    schedule = celery_app.conf.beat_schedule
    assert schedule["inventory-low-stock-scan"]["task"] == "inventory.low_stock_scan"
    assert "inventory.low_stock_scan" in celery_app.tasks
