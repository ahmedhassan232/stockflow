"""Create a demo company with realistic data.

    python -m app.scripts.seed_demo

Everything goes through the real HTTP API (in-process), so the demo data obeys exactly
the same validation, permissions, stock ledger and numbering rules as production data.
Safe to re-run: if the demo company already has products nothing is added.
Refuses to run when APP_ENV=production.
"""

import asyncio
import sys
import uuid

import httpx

from app.core.config import get_settings
from app.main import create_app

API = "/api/v1"
EMAIL = "owner@demo-nile.example.com"
PASSWORD = "StockFlow-Demo-2026"  # noqa: S105 - published demo credential, dev only

# name, sku, barcode, category, unit, cost, price, tax %, opening quantity, minimum level
PRODUCTS = [
    (
        "شاي العروسة 250 جم",
        "TEA-250",
        "6221031490017",
        "مشروبات",
        "علبة",
        "38.00",
        "48.00",
        "14",
        120,
        20,
    ),
    (
        "قهوة تركي 200 جم",
        "COF-200",
        "6221031490024",
        "مشروبات",
        "علبة",
        "72.50",
        "95.00",
        "14",
        60,
        10,
    ),
    (
        "مياه معدنية 1.5 لتر",
        "WAT-150",
        "6221031490031",
        "مشروبات",
        "زجاجة",
        "5.25",
        "8.00",
        "14",
        300,
        48,
    ),
    ("أرز مصري 1 كجم", "RIC-001", "6221031490048", "بقالة", "كيس", "27.00", "34.00", "0", 200, 30),
    ("سكر أبيض 1 كجم", "SUG-001", "6221031490055", "بقالة", "كيس", "29.50", "36.00", "0", 180, 30),
    (
        "زيت عباد الشمس 1 لتر",
        "OIL-001",
        "6221031490062",
        "بقالة",
        "زجاجة",
        "68.00",
        "82.00",
        "0",
        90,
        15,
    ),
    ("مكرونة 400 جم", "PAS-400", "6221031490079", "بقالة", "كيس", "11.00", "15.00", "0", 240, 40),
    (
        "صابون سائل 500 مل",
        "SOP-500",
        "6221031490086",
        "منظفات",
        "زجاجة",
        "33.00",
        "45.00",
        "14",
        70,
        12,
    ),
    (
        "مسحوق غسيل 2.5 كجم",
        "DET-250",
        "6221031490093",
        "منظفات",
        "علبة",
        "118.00",
        "149.00",
        "14",
        12,
        10,
    ),
    (
        "مناديل ورقية 550 منديل",
        "TIS-550",
        "6221031490109",
        "منظفات",
        "علبة",
        "21.00",
        "28.50",
        "14",
        150,
        24,
    ),
]
# (lines [(sku, qty, discount)], customer index | None, cash | card | wallet | credit | half)
SALES = [
    ([("TEA-250", "2", "0"), ("SUG-001", "3", "0")], None, "cash"),
    ([("WAT-150", "12", "6.00"), ("TIS-550", "2", "0")], 1, "card"),
    ([("RIC-001", "10", "0"), ("OIL-001", "4", "8.00"), ("PAS-400", "12", "0")], 0, "credit"),
    ([("COF-200", "1", "0"), ("TEA-250", "1", "0")], None, "cash"),
    ([("DET-250", "4", "0"), ("SOP-500", "3", "0")], 1, "half"),
    ([("WAT-150", "24", "0")], None, "cash"),
    ([("SUG-001", "5", "0"), ("RIC-001", "5", "0"), ("PAS-400", "6", "0")], 0, "wallet"),
]


class Seeder:
    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.h: dict[str, str] = {}

    async def call(self, method: str, path: str, body: dict | None = None, **params):
        headers = {**self.h, "Idempotency-Key": str(uuid.uuid4())} if method == "POST" else self.h
        r = await self.c.request(method, f"{API}{path}", json=body, params=params, headers=headers)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text}")
        return r.json()["data"]

    async def ensure(self, path: str, body: dict) -> dict:
        """Get-or-create by exact name, so an interrupted run can simply be repeated."""
        found = (await self.call("GET", path, q=body["name"], page_size=100))["items"]
        for item in found:
            if item["name"] == body["name"]:
                return item
        return await self.call("POST", path, body)

    async def sign_in(self) -> None:
        r = await self.c.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            r = await self.c.post(
                f"{API}/auth/register",
                json={
                    "full_name": "سارة أحمد",
                    "email": EMAIL,
                    "password": PASSWORD,
                    "company": {"name": "النيل للتجارة", "slug": "nile-trading"},
                },
            )
            if r.status_code != 201:
                raise SystemExit(f"cannot sign in or register the demo owner: {r.text}")
        data = r.json()["data"]
        self.h = {"Authorization": f"Bearer {data['access_token']}"}
        if not data.get("active_tenant_id"):
            me = await self.call("GET", "/auth/me")
            chosen = await self.call(
                "POST", "/auth/select-company", {"tenant_id": me["companies"][0]["tenant_id"]}
            )
            self.h = {"Authorization": f"Bearer {chosen['access_token']}"}

    async def seed_expenses(self) -> None:
        if (await self.call("GET", "/expenses", page_size=1))["total"] > 0:
            return
        day = (await self.call("GET", "/reports/dashboard"))["today"]  # company-local date
        for category, amount, note in (
            ("إيجار", "350.00", "إيجار المحل - دفعة"),
            ("كهرباء ومياه", "85.50", "فاتورة الكهرباء"),
            ("نقل وشحن", "40.00", "توصيل بضاعة"),
        ):
            await self.call(
                "POST",
                "/expenses",
                {"expense_date": day, "category": category, "amount": amount, "description": note},
            )
        print("  3 demo expenses recorded")

    async def run(self) -> None:
        await self.sign_in()
        await self.seed_expenses()
        if (await self.call("GET", "/products", page_size=1))["total"] > 0:
            print("Demo company already has products - nothing more to do.")
            return
        await self.call(
            "PATCH",
            "/settings",
            {"default_tax_rate": "14.00", "invoice_footer": "شكرًا لتعاملكم معنا"},
        )
        warehouse = (await self.call("GET", "/warehouses", q="MAIN"))["items"][0]["id"]
        categories = {
            n: (await self.ensure("/categories", {"name": n}))["id"]
            for n in sorted({p[3] for p in PRODUCTS})
        }
        units = {
            n: (await self.ensure("/units", {"name": n, "abbreviation": n}))["id"]
            for n in sorted({p[4] for p in PRODUCTS})
        }
        supplier = await self.ensure(
            "/suppliers", {"name": "شركة الدلتا للتوريدات", "phone": "+201000000001"}
        )
        customers = [
            await self.ensure("/customers", {"name": name, "phone": phone})
            for name, phone in (
                ("سوبر ماركت الأمل", "+201100000002"),
                ("كافيه المحطة", "+201200000003"),
            )
        ]
        products: dict[str, dict] = {}
        for name, sku, barcode, cat, unit, cost, price, tax, _qty, _minimum in PRODUCTS:
            products[sku] = await self.call(
                "POST",
                "/products",
                {
                    "name": name,
                    "sku": sku,
                    "barcode": barcode,
                    "category_id": categories[cat],
                    "unit_id": units[unit],
                    "purchase_price": cost,
                    "selling_price": price,
                    "tax_rate": tax,
                },
            )
        # Opening stock arrives the normal way: a purchase order that is then received.
        order = await self.call(
            "POST",
            "/purchases",
            {
                "supplier_id": supplier["id"],
                "warehouse_id": warehouse,
                "notes": "رصيد افتتاحي",
                "items": [
                    {"product_id": products[p[1]]["id"], "quantity": str(p[8]), "unit_cost": p[5]}
                    for p in PRODUCTS
                ],
            },
        )
        order = await self.call("POST", f"/purchases/{order['id']}/receive", {})
        await self.call(
            "POST",
            f"/purchases/{order['id']}/payments",
            {"amount": "20000.00", "method": "bank_transfer"},
        )
        for p in PRODUCTS:
            await self.call(
                "PUT",
                "/inventory/minimum-level",
                {
                    "warehouse_id": warehouse,
                    "product_id": products[p[1]]["id"],
                    "minimum_stock_level": str(p[9]),
                },
            )
        for lines, customer, pay in SALES:
            body = {
                "warehouse_id": warehouse,
                "customer_id": customers[customer]["id"] if customer is not None else None,
                "items": [
                    {"product_id": products[sku]["id"], "quantity": qty, "discount_amount": disc}
                    for sku, qty, disc in lines
                ],
            }
            sale = await self._sell(body, pay)
            print(f"  {sale['number']}  total {sale['total']}  ({sale['payment_status']})")
        print(f"Demo data ready. Sign in as {EMAIL} / {PASSWORD}")

    async def _sell(self, body: dict, pay: str) -> dict:
        """Walk-in sales are paid in cash at the till (the server returns the change).
        Account customers buy on credit; some then settle part or all of the balance,
        always using the amount the SERVER reports - the seed never computes money."""
        if pay == "cash":
            cash = [{"method": "cash", "amount": "5000.00"}]
            return await self.call("POST", "/sales", {**body, "payments": cash})
        sale = await self.call("POST", "/sales", body)
        if pay == "credit":
            return sale
        amount = "200.00" if pay == "half" else sale["balance_due"]
        method = "cash" if pay == "half" else pay
        return await self.call(
            "POST", f"/sales/{sale['id']}/payments", {"amount": amount, "method": method}
        )


async def main() -> None:
    if get_settings().is_production:
        sys.exit("Refusing to seed demo data when APP_ENV=production.")
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        await Seeder(client).run()


if __name__ == "__main__":
    asyncio.run(main())
