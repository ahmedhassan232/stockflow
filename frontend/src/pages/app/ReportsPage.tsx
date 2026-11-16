import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Printer } from "lucide-react";
import { ExportButton } from "@/components/common/ExportButton";
import { Button } from "@/components/ui/button";
import { ErrorAlert, PageHeader, Stat, Tabs } from "@/components/common/data";
import { useMoney } from "@/components/common/pickers";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/store";
import { useGet } from "@/features/data/api";
import { SalesChart, TopProducts, type DayRow, type TopProduct } from "@/pages/app/DashboardPage";

interface Summary {
  invoice_count: number;
  gross_sales: string;
  tax_collected: string;
  discounts: string;
  returns: string;
  average_invoice: string;
  revenue?: string;
  cogs?: string;
  gross_profit?: string;
  margin_percent?: string;
  expenses?: string;
  net_profit?: string;
}
interface Report {
  expenses?: { total: string; by_category: { category: string; amount: string }[] } | null;
  summary: Summary;
  by_day: DayRow[];
  top_products: TopProduct[];
  by_payment_method?: { method: string; received: string; refunded: string; net: string }[];
  by_cashier?: { user_id: string; name: string; invoice_count: number; gross_sales: string }[];
  receivables?: { total: string; customers: { customer_id: string; name: string; invoice_count: number; balance: string }[] };
  payables_total?: string;
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function ReportsPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const canSales = useCan("reports.sales.view");
  const canProfit = useCan("reports.financial.view");
  const [tab, setTab] = useState<"sales" | "profit">(canSales ? "sales" : "profit");
  const today = new Date();
  const [from, setFrom] = useState(iso(new Date(today.getTime() - 29 * 864e5)));
  const [to, setTo] = useState(iso(today));
  const validRange = !!from && !!to && from <= to;
  const query = useGet<Report>(`/reports/${tab}`, { date_from: from, date_to: to }, validRange);
  const r = query.data;
  const tabs = [...(canSales ? [{ key: "sales" as const, label: t("reports.salesTab") }] : []), ...(canProfit ? [{ key: "profit" as const, label: t("reports.profitTab") }] : [])];
  const dateInput = "h-10 rounded-md border bg-card px-3 text-sm";

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("reports.title")} subtitle={t("reports.subtitle")}>
        <label className="flex items-center gap-2 text-sm">
          {t("reports.from")}
          <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={dateInput} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          {t("reports.to")}
          <input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className={dateInput} />
        </label>
        {validRange ? <ExportButton path={`/reports/${tab}/export`} params={{ date_from: from, date_to: to }} filename={`${tab}-${from}_${to}.csv`} /> : null}
        {validRange ? <ExportButton kind="pdf" path={`/reports/${tab}/pdf`} params={{ date_from: from, date_to: to, lang: i18n.language.startsWith("ar") ? "ar" : "en" }} filename={`${tab}-${from}_${to}.pdf`} /> : null}
        <Button variant="outline" className="print:hidden" onClick={() => window.print()}>
          <Printer />
          {t("export.print")}
        </Button>
      </PageHeader>
      {tabs.length > 1 ? <Tabs tabs={tabs} value={tab} onChange={setTab} /> : null}
      {!validRange ? (
        <p role="alert" className="text-sm text-danger">{t("errors.INVALID_RANGE")}</p>
      ) : query.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : query.isError || !r ? (
        <ErrorAlert error={query.error} />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {tab === "profit" ? (
              <>
                <Stat label={t("reports.revenue")} value={<bdi>{money(r.summary.revenue)}</bdi>} hint={t("reports.revenueHint")} />
                <Stat label={t("reports.cogs")} value={<bdi>{money(r.summary.cogs)}</bdi>} hint={t("reports.cogsHint")} />
                <Stat label={t("reports.profit")} value={<bdi>{money(r.summary.gross_profit)}</bdi>} tone="success" />
                <Stat label={t("reports.margin")} value={<bdi>{r.summary.margin_percent}%</bdi>} />
                {r.summary.net_profit !== undefined ? (
                  <>
                    <Stat label={t("reports.expenses")} value={<bdi>{money(r.summary.expenses)}</bdi>} hint={t("reports.expensesHint")} />
                    <Stat label={t("reports.netProfit")} value={<bdi>{money(r.summary.net_profit)}</bdi>} hint={t("reports.netProfitHint")} tone={r.summary.net_profit.startsWith("-") ? "danger" : "success"} />
                  </>
                ) : null}
              </>
            ) : (
              <>
                <Stat label={t("reports.grossSales")} value={<bdi>{money(r.summary.gross_sales)}</bdi>} hint={t("dashboard.invoices", { count: r.summary.invoice_count })} />
                <Stat label={t("reports.average")} value={<bdi>{money(r.summary.average_invoice)}</bdi>} />
                <Stat label={t("reports.taxCollected")} value={<bdi>{money(r.summary.tax_collected)}</bdi>} />
                <Stat label={t("reports.returns")} value={<bdi>{money(r.summary.returns)}</bdi>} hint={`${t("fields.discount")}: ${money(r.summary.discounts)}`} />
              </>
            )}
          </div>
          <Card>
            <h2 className="px-5 pt-5 font-semibold">{t(tab === "profit" ? "reports.profitByDay" : "reports.salesByDay")}</h2>
            <div className="p-4">
              {r.summary.invoice_count === 0 && Number(r.summary.returns) === 0 ? <p className="grid h-64 place-items-center text-sm text-muted-foreground">{t("reports.noData")}</p> : <SalesChart rows={r.by_day} dataKey={tab === "profit" ? "gross_profit" : "gross_sales"} />}
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <h2 className="px-5 pb-2 pt-5 font-semibold">{t("dashboard.topProducts")}</h2>
              <TopProducts rows={r.top_products} />
            </Card>
            {r.by_payment_method ? (
              <Card>
                <h2 className="px-5 pb-2 pt-5 font-semibold">{t("reports.byMethod")}</h2>
                {r.by_payment_method.length === 0 ? (
                  <p className="p-6 text-center text-sm text-muted-foreground">{t("reports.noData")}</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {r.by_payment_method.map((m) => (
                      <li key={m.method} className="flex items-center justify-between px-5 py-3">
                        <span>{t(`method.${m.method}`)}</span>
                        <span className="text-end">
                          <bdi className="block font-semibold tabular-nums">{money(m.net)}</bdi>
                          {Number(m.refunded) > 0 ? <span className="text-xs text-muted-foreground">{t("reports.refunded")}: {money(m.refunded)}</span> : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {r.by_cashier?.length ? (
                  <>
                    <h2 className="border-t px-5 pb-2 pt-4 font-semibold">{t("reports.byCashier")}</h2>
                    <ul className="divide-y text-sm">
                      {r.by_cashier.map((c) => (
                        <li key={c.user_id} className="flex items-center justify-between px-5 py-3">
                          <span>
                            {c.name} <span className="text-xs text-muted-foreground">· {t("dashboard.invoices", { count: c.invoice_count })}</span>
                          </span>
                          <bdi className="font-semibold tabular-nums">{money(c.gross_sales)}</bdi>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </Card>
            ) : null}
            {r.expenses && r.expenses.by_category.length > 0 ? (
              <Card>
                <h2 className="flex items-center justify-between px-5 pb-2 pt-5 font-semibold">
                  {t("reports.expensesByCategory")}
                  <bdi className="tabular-nums">{money(r.expenses.total)}</bdi>
                </h2>
                <ul className="divide-y text-sm">
                  {r.expenses.by_category.map((c) => (
                    <li key={c.category} className="flex items-center justify-between px-5 py-3">
                      <span>{c.category}</span>
                      <bdi className="font-semibold tabular-nums">{money(c.amount)}</bdi>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            {r.receivables ? (
              <Card>
                <h2 className="flex items-center justify-between px-5 pb-2 pt-5 font-semibold">
                  {t("dashboard.receivables")}
                  <bdi className="tabular-nums">{money(r.receivables.total)}</bdi>
                </h2>
                {r.receivables.customers.length === 0 ? (
                  <p className="p-6 text-center text-sm text-muted-foreground">{t("reports.noDebts")}</p>
                ) : (
                  <ul className="divide-y text-sm">
                    {r.receivables.customers.map((c) => (
                      <li key={c.customer_id} className="flex items-center justify-between px-5 py-3">
                        <span>{c.name}</span>
                        <bdi className="font-semibold tabular-nums">{money(c.balance)}</bdi>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="flex items-center justify-between border-t px-5 py-3 text-sm">
                  <span className="text-muted-foreground">{t("dashboard.payables")}</span>
                  <bdi className="font-semibold tabular-nums">{money(r.payables_total)}</bdi>
                </p>
              </Card>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
