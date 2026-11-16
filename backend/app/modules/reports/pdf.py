"""HTML bodies for the PDF documents (invoice, sales report, profit report)."""

from typing import Any, Literal

from app.core.pdf import e

Lang = Literal["ar", "en"]

_T: dict[str, tuple[str, str]] = {
    "invoice": ("فاتورة", "Invoice"),
    "date": ("التاريخ", "Date"),
    "customer": ("العميل", "Customer"),
    "walk_in": ("عميل نقدي", "Walk-in customer"),
    "cashier": ("البائع", "Cashier"),
    "tax_no": ("الرقم الضريبي", "Tax number"),
    "product": ("المنتج", "Product"),
    "qty": ("الكمية", "Qty"),
    "price": ("السعر", "Price"),
    "discount": ("الخصم", "Discount"),
    "tax": ("الضريبة", "Tax"),
    "line_total": ("الإجمالي", "Total"),
    "subtotal": ("الإجمالي قبل الضريبة", "Subtotal"),
    "total": ("الإجمالي", "Total"),
    "paid": ("المدفوع", "Paid"),
    "returned": ("المرتجع", "Returned"),
    "balance": ("المتبقي", "Balance due"),
    "cancelled": ("ملغاة", "VOID"),
    "sales_report": ("تقرير المبيعات", "Sales report"),
    "profit_report": ("تقرير الأرباح", "Profit report"),
    "period": ("الفترة", "Period"),
    "invoices": ("عدد الفواتير", "Invoices"),
    "gross_sales": ("إجمالي المبيعات (شامل الضريبة)", "Gross sales (incl. tax)"),
    "tax_collected": ("الضريبة المحصّلة", "Tax collected"),
    "returns": ("المرتجعات", "Returns"),
    "average": ("متوسط الفاتورة", "Average invoice"),
    "revenue": ("صافي الإيراد", "Net revenue"),
    "cogs": ("تكلفة البضاعة المباعة", "Cost of goods sold"),
    "gross_profit": ("مجمل الربح", "Gross profit"),
    "margin": ("هامش الربح", "Margin"),
    "expenses": ("المصروفات", "Expenses"),
    "net_profit": ("صافي الربح", "Net profit"),
    "by_day": ("حسب اليوم", "By day"),
    "top_products": ("الأكثر مبيعًا", "Top products"),
    "by_category": ("المصروفات حسب البند", "Expenses by category"),
    "category": ("البند", "Category"),
    "amount": ("المبلغ", "Amount"),
}


def _t(lang: Lang):
    index = 0 if lang == "ar" else 1
    return lambda key: _T[key][index]


def _table(headers: list[tuple[str, bool]], rows: list[list[Any]]) -> str:
    head = "".join(f'<th class="{"num" if num else ""}">{e(h)}</th>' for h, num in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"num" if headers[i][1] else ""}">{e(v)}</td>' for i, v in enumerate(r)
        )
        + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _header(company: Any, title: str, lines: list[str]) -> str:
    details = " · ".join(e(v) for v in (company.address, company.phone) if v)
    return (
        '<div class="head"><div class="row"><div>'
        f"<h1>{e(company.name)}</h1><div class='muted'>{details}</div></div>"
        f"<div style='text-align:end'><h1>{e(title)}</h1>"
        + "".join(f"<div class='muted'>{line}</div>" for line in lines)
        + "</div></div></div>"
    )


def invoice_html(sale: Any, company: Any, settings: Any, lang: Lang) -> str:
    t = _t(lang)
    cur = e(company.currency)
    when = sale.created_at.astimezone(_zone(company)).strftime("%Y-%m-%d %H:%M")
    title = f"{t('invoice')} {sale.number}"
    if sale.status == "cancelled":
        title += f" ({t('cancelled')})"
    meta = [f"{t('date')}: <bdi>{e(when)}</bdi>"]
    if settings.tax_number:
        meta.append(f"{t('tax_no')}: <bdi>{e(settings.tax_number)}</bdi>")
    info = (
        f"<div class='row'><div>{t('customer')}: <b>{e(sale.customer_name or t('walk_in'))}</b></div>"
        f"<div>{t('cashier')}: {e(sale.cashier_name)}</div></div>"
    )
    items = _table(
        [
            (t("product"), False),
            (t("qty"), True),
            (t("price"), True),
            (t("discount"), True),
            (t("tax"), True),
            (t("line_total"), True),
        ],
        [
            [
                i.product_name,
                i.quantity,
                i.unit_price,
                i.discount_amount,
                i.tax_amount,
                i.line_total,
            ]
            for i in sale.items
        ],
    )
    rows = [
        (t("subtotal"), sale.subtotal, ""),
        (t("discount"), sale.discount_amount, ""),
        (t("tax"), sale.tax_amount, ""),
        (t("total"), sale.total, "grand"),
        (t("paid"), sale.paid_amount, ""),
        (t("returned"), sale.returned_amount, ""),
        (t("balance"), sale.balance_due, ""),
    ]
    totals = "".join(
        f'<tr class="{cls}"><td>{e(label)}</td><td class="num">{e(value)} {cur}</td></tr>'
        for label, value, cls in rows
        if cls or label in (t("subtotal"), t("tax"), t("paid")) or value != 0
    )
    footer = (
        f"<div class='foot'>{e(settings.invoice_footer)}</div>" if settings.invoice_footer else ""
    )
    return (
        _header(company, title, meta)
        + info
        + items
        + f"<table class='totals'>{totals}</table>"
        + footer
    )


def _zone(company: Any):
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(company.timezone)
    except Exception:
        return ZoneInfo("UTC")


def report_html(
    kind: Literal["sales", "profit"], report: dict, company: Any, start, end, lang: Lang
) -> str:
    t = _t(lang)
    cur = company.currency
    s = report["summary"]

    def card(label: str, value: Any, suffix: str = "") -> str:
        return f"<div class='card'><span class='muted'>{e(label)}</span><b>{e(value)}{e(suffix)}</b></div>"

    money = f" {cur}"
    if kind == "profit":
        cards = [
            card(t("revenue"), s["revenue"], money),
            card(t("cogs"), s["cogs"], money),
            card(t("gross_profit"), s["gross_profit"], money),
            card(t("margin"), s["margin_percent"], "%"),
        ]
        if "net_profit" in s:
            cards += [
                card(t("expenses"), s["expenses"], money),
                card(t("net_profit"), s["net_profit"], money),
            ]
        days = _table(
            [
                (t("date"), False),
                (t("invoices"), True),
                (t("revenue"), True),
                (t("cogs"), True),
                (t("gross_profit"), True),
            ],
            [
                [d["date"], d["invoice_count"], d["revenue"], d["cogs"], d["gross_profit"]]
                for d in report["by_day"]
                if d["invoice_count"] or d["revenue"]
            ],
        )
    else:
        cards = [
            card(t("gross_sales"), s["gross_sales"], money),
            card(t("invoices"), s["invoice_count"]),
            card(t("average"), s["average_invoice"], money),
            card(t("tax_collected"), s["tax_collected"], money),
            card(t("returns"), s["returns"], money),
        ]
        days = _table(
            [(t("date"), False), (t("invoices"), True), (t("gross_sales"), True)],
            [
                [d["date"], d["invoice_count"], d["gross_sales"]]
                for d in report["by_day"]
                if d["invoice_count"]
            ],
        )
    top = _table(
        [(t("product"), False), (t("qty"), True), (t("revenue"), True)],
        [[p["name"], p["quantity"], p["revenue"]] for p in report["top_products"]],
    )
    out = (
        _header(company, t(f"{kind}_report"), [f"{t('period')}: <bdi>{e(start)} → {e(end)}</bdi>"])
        + f"<div class='cards'>{''.join(cards)}</div>"
        + f"<h2>{t('by_day')}</h2>{days}<h2>{t('top_products')}</h2>{top}"
    )
    expenses = report.get("expenses")
    if expenses and expenses["by_category"]:
        out += f"<h2>{t('by_category')}</h2>" + _table(
            [(t("category"), False), (t("amount"), True)],
            [[c["category"], c["amount"]] for c in expenses["by_category"]],
        )
    return out
