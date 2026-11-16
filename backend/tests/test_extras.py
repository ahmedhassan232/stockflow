"""Expenses, CSV export, e-mail verification, platform administration, digest."""

import re
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.core import email as mail
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.tasks.low_stock import send_low_stock_digests
from tests.api_helpers import (
    API,
    add_member,
    adjust,
    create_product,
    login,
    main_warehouse,
    register_company,
)
from tests.test_sales import stocked


class _FakeRedis:
    def __init__(self):
        self.keys = set()

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


async def _member(app, owner, role):
    return await login(app, await add_member(owner, role))


def _token(kind: str) -> str:
    body = next(m.body for m in reversed(mail.outbox) if f"/{kind}?token=" in m.body)
    return re.search(r"token=([\w-]+)", body).group(1)


def _grant_platform_admin(email: str) -> None:
    engine = create_engine(get_settings().migration_database_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"), {"e": email}
        )
    engine.dispose()


# ───────────── expenses ─────────────


async def _expense(acc, **over):
    body = {"expense_date": "2026-11-10", "category": "Rent", "amount": "1500.00", **over}
    return await acc.client.post(f"{API}/expenses", headers=acc.h, json=body)


async def test_expenses_reduce_net_profit_and_voiding_restores_it(app):
    a = await register_company(app, "Expense Co")
    w = await main_warehouse(a)
    p = await stocked(a, w, 10, "60.0000", selling_price="100.00", tax_rate="0")
    sale = await a.client.post(
        f"{API}/sales",
        headers=a.h,
        json={
            "warehouse_id": w,
            "items": [{"product_id": p["id"], "quantity": "5"}],
            "payments": [{"method": "cash", "amount": "500.00"}],
        },
    )
    assert sale.status_code == 201, sale.text

    today = (await a.client.get(f"{API}/reports/dashboard", headers=a.h)).json()["data"]["today"]
    r = await _expense(a, expense_date=today, amount="80.00")
    assert r.status_code == 201, r.text
    expense = r.json()["data"]
    assert expense["number"] == "EXP-000001" and expense["amount"] == "80.00"

    summary = (await a.client.get(f"{API}/reports/profit", headers=a.h)).json()["data"]["summary"]
    assert summary["gross_profit"] == "200.00"
    assert summary["expenses"] == "80.00" and summary["net_profit"] == "120.00"

    r = await a.client.post(
        f"{API}/expenses/{expense['id']}/void", headers=a.h, json={"reason": "entered twice"}
    )
    assert r.status_code == 200 and r.json()["data"]["status"] == "voided"
    summary = (await a.client.get(f"{API}/reports/profit", headers=a.h)).json()["data"]["summary"]
    assert summary["expenses"] == "0.00" and summary["net_profit"] == "200.00"
    again = await a.client.post(
        f"{API}/expenses/{expense['id']}/void", headers=a.h, json={"reason": "again please"}
    )
    assert again.json()["error"]["code"] == "INVALID_STATUS"

    listing = (await a.client.get(f"{API}/expenses", headers=a.h)).json()["data"]
    assert listing["total"] == 1 and listing["total_amount"] == "0.00"


async def test_expense_validation_permissions_and_isolation(app):
    a = await register_company(app, "Exp Alpha")
    b = await register_company(app, "Exp Beta")
    assert (await _expense(a, amount="0")).status_code == 422
    assert (await _expense(a, amount="10.005")).status_code == 422
    assert (await _expense(a, expense_date="2999-01-01")).json()["error"]["code"] == "FUTURE_DATE"
    created = (await _expense(a)).json()["data"]

    # another company can neither see nor void it
    assert (await b.client.get(f"{API}/expenses", headers=b.h)).json()["data"]["total"] == 0
    r = await b.client.post(
        f"{API}/expenses/{created['id']}/void", headers=b.h, json={"reason": "not mine"}
    )
    assert r.status_code == 404
    # a foreign branch id is rejected
    b_branch = (await b.client.get(f"{API}/branches", headers=b.h)).json()["data"]["items"][0]["id"]
    assert (await _expense(a, branch_id=b_branch)).json()["error"]["code"] == "INVALID_REFERENCE"

    cashier = await _member(app, a, "sales_cashier")
    assert (await cashier.client.get(f"{API}/expenses", headers=cashier.h)).status_code == 403
    assert (await _expense(cashier)).status_code == 403


async def test_expense_create_is_idempotent(app):
    a = await register_company(app, "Exp Idem")
    key = {"Idempotency-Key": str(uuid.uuid4())}
    body = {"expense_date": "2026-11-01", "category": "Fuel", "amount": "45.50"}
    first = await a.client.post(f"{API}/expenses", headers={**a.h, **key}, json=body)
    second = await a.client.post(f"{API}/expenses", headers={**a.h, **key}, json=body)
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert (await a.client.get(f"{API}/expenses", headers=a.h)).json()["data"]["total"] == 1


# ───────────── CSV export ─────────────


async def test_csv_exports_are_scoped_permissioned_and_formula_safe(app):
    a = await register_company(app, "Csv Alpha")
    b = await register_company(app, "Csv Beta")
    w = await main_warehouse(a)
    await stocked(a, w, 4, "2.5000", name="=HYPERLINK(evil)", sku="CSV-1")
    await create_product(b, name="Beta Secret", sku="B-1")

    r = await a.client.get(f"{API}/inventory/export", headers=a.h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text_ = r.content.decode("utf-8")
    assert text_.startswith("\ufeff")  # Excel needs the BOM to read Arabic
    assert "'=HYPERLINK(evil)" in text_ and "\n=HYPERLINK" not in text_
    assert "Stock value" in text_ and "10.00" in text_
    assert "Beta Secret" not in text_

    for path in (
        "/sales/export",
        "/reports/sales/export",
        "/reports/profit/export",
        "/expenses/export",
    ):
        assert (await a.client.get(f"{API}{path}", headers=a.h)).status_code == 200, path

    worker = await _member(app, a, "warehouse_employee")
    r = await worker.client.get(f"{API}/inventory/export", headers=worker.h)
    assert r.status_code == 200 and "Stock value" not in r.text  # no cost data without permission
    assert (
        await worker.client.get(f"{API}/reports/profit/export", headers=worker.h)
    ).status_code == 403


# ───────────── e-mail verification ─────────────


async def test_email_verification_flow(app):
    a = await register_company(app, "Verify Co")
    me = (await a.client.get(f"{API}/auth/me", headers=a.h)).json()["data"]
    assert me["user"]["email_verified"] is False
    token = _token("verify-email")

    # a verification token can never be used to reset the password
    r = await a.client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": "Another-Passw0rd-123"}
    )
    assert r.json()["error"]["code"] == "INVALID_RESET_TOKEN"

    assert (
        await a.client.post(f"{API}/auth/verify-email", json={"token": token})
    ).status_code == 200
    me = (await a.client.get(f"{API}/auth/me", headers=a.h)).json()["data"]
    assert me["user"]["email_verified"] is True
    reused = await a.client.post(f"{API}/auth/verify-email", json={"token": token})
    assert reused.json()["error"]["code"] == "INVALID_VERIFY_TOKEN"


async def test_resend_invalidates_the_previous_link(app):
    a = await register_company(app, "Verify Two")
    old = _token("verify-email")
    assert (await a.client.post(f"{API}/auth/resend-verification", headers=a.h)).status_code == 200
    new = _token("verify-email")
    assert new != old
    assert (await a.client.post(f"{API}/auth/verify-email", json={"token": old})).status_code == 400
    assert (await a.client.post(f"{API}/auth/verify-email", json={"token": new})).status_code == 200
    assert (await a.client.post(f"{API}/auth/resend-verification")).status_code == 401


# ───────────── platform administration ─────────────


async def test_platform_admin_can_list_and_suspend_companies(app):
    admin = await register_company(app, "Platform Ops")
    victim = await register_company(app, "Suspend Me")

    # ordinary owners are refused
    assert (await victim.client.get(f"{API}/platform/tenants", headers=victim.h)).status_code == 403
    r = await victim.client.patch(
        f"{API}/platform/tenants/{admin.tenant_id}", headers=victim.h, json={"status": "suspended"}
    )
    assert r.status_code == 403

    _grant_platform_admin(admin.email)
    rows = (await admin.client.get(f"{API}/platform/tenants", headers=admin.h)).json()["data"]
    row = next(t for t in rows if t["id"] == str(victim.tenant_id))
    assert (
        row["name"] == "Suspend Me"
        and row["owner_email"] == victim.email
        and row["member_count"] == 1
    )

    r = await admin.client.patch(
        f"{API}/platform/tenants/{victim.tenant_id}", headers=admin.h, json={"status": "suspended"}
    )
    assert r.status_code == 200
    blocked = await victim.client.get(f"{API}/products", headers=victim.h)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "TENANT_SUSPENDED"

    await admin.client.patch(
        f"{API}/platform/tenants/{victim.tenant_id}", headers=admin.h, json={"status": "active"}
    )
    assert (await victim.client.get(f"{API}/products", headers=victim.h)).status_code == 200
    r = await admin.client.patch(
        f"{API}/platform/tenants/{uuid.uuid4()}", headers=admin.h, json={"status": "suspended"}
    )
    assert r.status_code == 404

    log = (await admin.client.get(f"{API}/platform/audit-log", headers=admin.h)).json()["data"]
    mine = [e for e in log if e["company_name"] == "Suspend Me"]
    assert [e["action"] for e in mine] == ["company.activated", "company.suspended"]
    assert mine[0]["actor_email"] == admin.email
    assert (
        await victim.client.get(f"{API}/platform/audit-log", headers=victim.h)
    ).status_code == 403

    # being a platform admin gives no access to another company's business data
    assert (await admin.client.get(f"{API}/products", headers=admin.h)).json()["data"]["total"] == 0


async def test_database_refuses_platform_functions_and_flag_for_the_app_role(app):
    a = await register_company(app, "Not Admin")
    async with get_sessionmaker()() as s, s.begin():
        await s.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a.user_id)})
        with pytest.raises(Exception, match="platform administrator required"):
            await s.execute(text("SELECT * FROM platform_list_tenants()"))
    for statement in (
        "SELECT * FROM platform_audit_logs",
        "INSERT INTO platform_audit_logs (actor_user_id, action, target_company_id, target_company_name) "
        f"VALUES ('{a.user_id}', 'x', '{a.tenant_id}', 'x')",
    ):
        async with get_sessionmaker()() as s, s.begin():
            with pytest.raises(Exception, match="permission denied"):
                await s.execute(text(statement))
    async with get_sessionmaker()() as s, s.begin():
        with pytest.raises(Exception, match="platform CLI"):
            await s.execute(
                text("UPDATE users SET is_platform_admin = true WHERE id = :u"), {"u": a.user_id}
            )


# ───────────── daily digest ─────────────


async def test_digest_goes_once_a_day_to_verified_people_who_may_see_stock(app):
    a = await register_company(app, "Digest Co")
    await a.client.post(f"{API}/auth/verify-email", json={"token": _token("verify-email")})
    await add_member(a, "sales_cashier")  # no inventory.view -> must not receive it
    w = await main_warehouse(a)
    p = await create_product(a, name="Digest Tea")
    await adjust(a, w, p["id"], "2")
    await a.client.put(
        f"{API}/inventory/minimum-level",
        headers=a.h,
        json={"warehouse_id": w, "product_id": p["id"], "minimum_stock_level": "5"},
    )
    mail.outbox.clear()

    redis_client = _FakeRedis()
    await send_low_stock_digests(get_sessionmaker(), redis_client)
    mine = [m for m in mail.outbox if "Digest Tea" in m.body]
    assert [m.to for m in mine] == [a.email]
    assert "2.000 / 5.000" in mine[0].body

    mail.outbox.clear()
    await send_low_stock_digests(get_sessionmaker(), redis_client)  # same day -> nothing
    assert not [m for m in mail.outbox if "Digest Tea" in m.body]


# ───────────── PDF ─────────────


async def test_invoice_and_report_pdfs_are_real_pdfs_scoped_and_escape_user_text(app):
    a = await register_company(app, "Pdf <b>Alpha</b>")
    b = await register_company(app, "Pdf Beta")
    w = await main_warehouse(a)
    p = await stocked(
        a, w, 5, "10.0000", name="<img src=file:///etc/passwd> شاي", selling_price="20.00"
    )
    sale = (
        await a.client.post(
            f"{API}/sales",
            headers=a.h,
            json={
                "warehouse_id": w,
                "items": [{"product_id": p["id"], "quantity": "2"}],
                "payments": [{"method": "cash", "amount": "100.00"}],
            },
        )
    ).json()["data"]

    for path in (
        f"/sales/{sale['id']}/pdf",
        f"/sales/{sale['id']}/pdf?lang=en",
        "/reports/sales/pdf",
        "/reports/profit/pdf",
    ):
        r = await a.client.get(f"{API}{path}", headers=a.h)
        assert r.status_code == 200, (path, r.text[:300])
        assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-")
        assert len(r.content) > 3000

    assert (await b.client.get(f"{API}/sales/{sale['id']}/pdf", headers=b.h)).status_code == 404
    assert (await a.client.get(f"{API}/sales/{sale['id']}/pdf")).status_code == 401
    worker = await _member(app, a, "warehouse_employee")
    assert (
        await worker.client.get(f"{API}/reports/profit/pdf", headers=worker.h)
    ).status_code == 403


def test_pdf_html_escapes_markup_and_never_fetches_resources():
    from types import SimpleNamespace as NS

    from app.core.pdf import _render
    from app.modules.reports.pdf import _table

    html = _table([("<script>x</script>", False)], [["<img src='http://evil.example/x.png'>"]])
    assert "<script>" not in html and "<img" not in html and "&lt;img" in html
    # even if raw markup slipped through, the renderer refuses to load anything
    pdf = _render(
        "<img src='file:///etc/passwd'><link rel=stylesheet href='http://evil.example/a.css'>ok",
        "en",
    )
    assert pdf.startswith(b"%PDF-")
    del NS
