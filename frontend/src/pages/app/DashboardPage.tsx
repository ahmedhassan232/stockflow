import { AlertTriangle, ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorAlert, Stat } from "@/components/common/data";
import { useMoney } from "@/components/common/pickers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth, useCan } from "@/features/auth/store";
import { useGet, useList } from "@/features/data/api";
import type { Balance } from "@/features/data/types";
import { formatDay, formatQty } from "@/utils/format";

interface Summary {
  invoice_count: number;
  gross_sales: string;
  returns: string;
  average_invoice: string;
  gross_profit?: string;
  margin_percent?: string;
}
export interface DayRow {
  date: string;
  invoice_count: number;
  gross_sales: string;
  revenue?: string;
  gross_profit?: string;
}
export interface TopProduct {
  product_id: string;
  name: string;
  sku: string;
  quantity: string;
  revenue: string;
  gross_profit?: string;
}
interface Dashboard {
  sales_today: Summary | null;
  sales_month: Summary | null;
  sales_by_day: DayRow[] | null;
  top_products: TopProduct[] | null;
  receivables_total: string | null;
  payables_total: string | null;
  inventory: { stock_value: string | null; low_stock_count: number; active_products: number } | null;
}

export function SalesChart({ rows, dataKey = "gross_sales" }: { rows: DayRow[]; dataKey?: "gross_sales" | "gross_profit" }) {
  const { i18n } = useTranslation();
  const money = useMoney();
  const rtl = i18n.dir() === "rtl";
  // Numbers are parsed only to draw bar heights; labels use the exact server strings.
  const data = rows.map((r) => ({ label: formatDay(r.date, i18n.language), value: Number(r[dataKey] ?? 0) }));
  return (
    <div className="h-64 w-full" dir="ltr">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
          <XAxis dataKey="label" reversed={rtl} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis orientation={rtl ? "right" : "left"} width={48} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
          <Tooltip cursor={{ fill: "hsl(var(--muted))" }} formatter={(v) => [money(Number(v)), ""]} separator="" contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="value" fill="hsl(var(--secondary))" radius={[4, 4, 0, 0]} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TopProducts({ rows }: { rows: TopProduct[] }) {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  if (rows.length === 0) return <p className="p-6 text-center text-sm text-muted-foreground">{t("dashboard.noSales")}</p>;
  return (
    <ul className="divide-y text-sm">
      {rows.map((p, index) => (
        <li key={p.product_id} className="flex items-center justify-between gap-3 px-5 py-3">
          <span className="flex min-w-0 items-center gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">{index + 1}</span>
            <span className="truncate">{p.name}</span>
          </span>
          <span className="shrink-0 text-end">
            <bdi className="block font-semibold tabular-nums">{money(p.revenue)}</bdi>
            <span className="text-xs text-muted-foreground">
              {t("dashboard.unitsSold", { count: Number(p.quantity), formatted: formatQty(p.quantity, i18n.language) })}
              {p.gross_profit !== undefined ? ` · ${t("reports.profit")}: ${money(p.gross_profit)}` : ""}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const me = useAuth((s) => s.me);
  const canSell = useCan("sales.create");
  const canStock = useCan("inventory.view");
  const query = useGet<Dashboard>("/reports/dashboard", undefined, true, 60_000);
  const low = useList<Balance>("/inventory/low-stock", { page_size: 5 }, canStock);
  const d = query.data;

  return (
    <section className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("org.overviewTitle", { name: me?.user.full_name ?? "" })}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {me?.active_company?.name} · {t(`roles.names.${me?.active_company?.role_code}`, { defaultValue: me?.active_company?.role_name })}
          </p>
        </div>
        {canSell ? (
          <Link to="/app/pos">
            <Button tabIndex={-1}>
              {t("dashboard.newSale")}
              <ArrowUpRight className="rtl:-scale-x-100" />
            </Button>
          </Link>
        ) : null}
      </div>

      {query.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : query.isError || !d ? (
        <ErrorAlert error={query.error} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {d.sales_today ? <Stat label={t("dashboard.salesToday")} value={<bdi>{money(d.sales_today.gross_sales)}</bdi>} hint={t("dashboard.invoices", { count: d.sales_today.invoice_count })} /> : null}
            {d.sales_month ? <Stat label={t("dashboard.salesMonth")} value={<bdi>{money(d.sales_month.gross_sales)}</bdi>} hint={t("dashboard.invoices", { count: d.sales_month.invoice_count })} /> : null}
            {d.sales_month?.gross_profit !== undefined ? <Stat label={t("dashboard.profitMonth")} value={<bdi>{money(d.sales_month.gross_profit)}</bdi>} hint={`${t("reports.margin")}: ${d.sales_month.margin_percent}%`} tone="success" /> : null}
            {d.inventory?.stock_value != null ? <Stat label={t("inventory.totalValue")} value={<bdi>{money(d.inventory.stock_value)}</bdi>} hint={t("dashboard.products", { count: d.inventory.active_products })} /> : null}
            {d.inventory ? <Stat label={t("inventory.lowCount")} value={d.inventory.low_stock_count} tone={d.inventory.low_stock_count ? "danger" : undefined} /> : null}
            {d.receivables_total != null ? <Stat label={t("dashboard.receivables")} value={<bdi>{money(d.receivables_total)}</bdi>} hint={t("dashboard.receivablesHint")} /> : null}
            {d.payables_total != null ? <Stat label={t("dashboard.payables")} value={<bdi>{money(d.payables_total)}</bdi>} hint={t("dashboard.payablesHint")} /> : null}
          </div>

          {!d.sales_today && !d.inventory ? <Card className="mt-4 p-8 text-center text-sm text-muted-foreground">{t("dashboard.nothing")}</Card> : null}

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            {d.sales_by_day ? (
              <Card className="lg:col-span-3">
                <h2 className="px-5 pt-5 font-semibold">{t("dashboard.last14")}</h2>
                <div className="p-4">
                  {d.sales_by_day.every((r) => r.invoice_count === 0) ? <p className="grid h-64 place-items-center text-sm text-muted-foreground">{t("dashboard.noSales")}</p> : <SalesChart rows={d.sales_by_day} />}
                </div>
              </Card>
            ) : null}
            {d.top_products ? (
              <Card className="lg:col-span-2">
                <h2 className="px-5 pb-2 pt-5 font-semibold">{t("dashboard.topProducts")}</h2>
                <TopProducts rows={d.top_products} />
              </Card>
            ) : null}
          </div>

          {canStock && low.data && low.data.items.length > 0 ? (
            <Card className="mt-4">
              <div className="flex items-center justify-between px-5 pt-5">
                <h2 className="flex items-center gap-2 font-semibold">
                  <AlertTriangle className="size-4 text-warning" aria-hidden="true" />
                  {t("inventory.lowStock")}
                </h2>
                <Link to="/app/inventory" className="text-sm text-secondary hover:underline">{t("dashboard.viewAll")}</Link>
              </div>
              <ul className="mt-2 divide-y text-sm">
                {low.data.items.map((b) => (
                  <li key={`${b.warehouse_id}:${b.product_id}`} className="flex items-center justify-between gap-3 px-5 py-3">
                    <span>
                      {b.product_name} <span className="text-xs text-muted-foreground">· {b.warehouse_name}</span>
                    </span>
                    <bdi className="font-semibold tabular-nums text-danger">
                      {formatQty(b.quantity, i18n.language)} / {formatQty(b.minimum_stock_level, i18n.language)}
                    </bdi>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </>
      )}
    </section>
  );
}
