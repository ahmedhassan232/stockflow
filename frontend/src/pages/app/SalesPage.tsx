import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ExportButton } from "@/components/common/ExportButton";
import { DataTable, ErrorAlert, PageHeader, SearchInput, type Column } from "@/components/common/data";
import { decimalInput, useMoney } from "@/components/common/pickers";
import { Receipt } from "@/components/common/Receipt";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/store";
import { newKey, useGet, useList, useSend } from "@/features/data/api";
import { PAYMENT_METHODS, type Sale } from "@/features/data/types";
import { compare, isPositive, parse, toFixed } from "@/utils/decimal";
import { formatDateTime, formatQty } from "@/utils/format";

const TONE = { paid: "success", partial: "warning", unpaid: "danger", cancelled: "neutral" } as const;

function Detail({ id, onClose }: { id: string; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const query = useGet<Sale>(`/sales/${id}`);
  const settings = useGet<{ invoice_footer: string | null }>("/settings", undefined, useCan("settings.view"));
  const send = useSend<Sale>(["sales", "inventory", "products", "reports"]);
  const can = { ret: useCan("sales.return"), cancel: useCan("sales.cancel"), pay: useCan("payments.manage") };
  const [mode, setMode] = useState<"view" | "return" | "cancel" | "pay">("view");
  const [key, setKey] = useState(newKey);
  const [qty, setQty] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<string>("cash");
  const [notice, setNotice] = useState<string | null>(null);
  const sale = query.data;
  if (query.isPending) return <Skeleton className="h-48" />;
  if (!sale) return <ErrorAlert error={query.error} />;

  const reset = () => {
    setMode("view");
    setQty({});
    setReason("");
    setAmount("");
    setKey(newKey());
  };
  const act = (path: string, body: unknown) =>
    send.mutate(
      { path: `/sales/${id}/${path}`, body, idempotencyKey: path === "cancel" ? undefined : key },
      {
        onSuccess: (result) => {
          setNotice(result.refund_amount && isPositive(result.refund_amount) ? t("sales.refundNotice", { amount: money(result.refund_amount) }) : null);
          reset();
        },
      },
    );
  const start = (next: typeof mode) => {
    send.reset();
    setNotice(null);
    setMode(next);
    if (next === "pay") setAmount(sale.balance_due);
  };
  const chosen = Object.entries(qty).filter(([, v]) => isPositive(v));
  const active = sale.status === "completed";
  const anyReturnable = (sale.items ?? []).some((i) => parse(i.quantity) > parse(i.returned_quantity));

  return (
    <div className="space-y-4">
      <ErrorAlert error={send.error} />
      {notice ? <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">{notice}</p> : null}

      {mode === "view" ? (
        <>
          <Receipt sale={sale} footer={settings.data?.invoice_footer} />
          <div className="flex justify-end print:hidden">
            <ExportButton kind="pdf" path={`/sales/${sale.id}/pdf`} params={{ lang: i18n.language.startsWith("ar") ? "ar" : "en" }} filename={`${sale.number}.pdf`} />
          </div>
          {(sale.payments ?? []).length ? (
            <div className="print:hidden">
              <h3 className="mb-2 text-sm font-semibold">{t("sales.payments")}</h3>
              <ul className="divide-y rounded-md border text-sm">
                {(sale.payments ?? []).map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <span>
                      {t(`method.${p.method}`)} <span className="text-xs text-muted-foreground">· {formatDateTime(p.created_at, i18n.language)}</span>
                    </span>
                    <bdi className={`tabular-nums ${p.direction === "out" ? "text-danger" : ""}`}>
                      {p.direction === "out" ? "−" : ""}
                      {money(p.amount)}
                    </bdi>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {mode === "return" ? (
        <>
          <p className="text-sm text-muted-foreground">{t("sales.returnHint")}</p>
          <ul className="divide-y rounded-md border text-sm">
            {(sale.items ?? []).map((i) => {
              const left = toFixed(parse(i.quantity) - parse(i.returned_quantity), 3);
              const over = compare(qty[i.id] || "0", left) > 0;
              return (
                <li key={i.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="min-w-0 flex-1">
                    {i.product_name}
                    <span className="block text-xs text-muted-foreground">{t("sales.returnable")}: {formatQty(left, i18n.language)}</span>
                  </span>
                  <input aria-label={i.product_name} dir="ltr" inputMode="decimal" disabled={!isPositive(left)} aria-invalid={over} className={decimalInput} value={qty[i.id] ?? ""} onChange={(e) => setQty((q) => ({ ...q, [i.id]: e.target.value }))} />
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      {mode === "cancel" ? <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm">{t("sales.cancelHint")}</p> : null}
      {mode === "return" || mode === "cancel" ? <TextField label={t("inventory.reason")} hint={t("inventory.reasonHint")} value={reason} onChange={(e) => setReason(e.target.value)} /> : null}
      {mode === "pay" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={t("fields.amount")} dir="ltr" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={compare(amount || "0", sale.balance_due) > 0 ? t("errors.OVERPAYMENT") : undefined} />
          <SelectField label={t("fields.method")} value={method} onChange={(e) => setMethod(e.target.value)}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>{t(`method.${m}`)}</option>
            ))}
          </SelectField>
        </div>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2 border-t pt-4 print:hidden">
        {mode === "view" ? (
          <>
            <Button variant="outline" onClick={onClose}>{t("org.close")}</Button>
            {active && can.cancel && !isPositive(sale.returned_amount) ? <Button variant="outline" className="text-danger" onClick={() => start("cancel")}>{t("sales.cancel")}</Button> : null}
            {active && can.ret && anyReturnable ? <Button variant="outline" onClick={() => start("return")}>{t("sales.return")}</Button> : null}
            {active && can.pay && isPositive(sale.balance_due) ? <Button onClick={() => start("pay")}>{t("sales.collect")}</Button> : null}
          </>
        ) : (
          <>
            <Button variant="outline" onClick={reset}>{t("common.back")}</Button>
            {mode === "return" ? (
              <Button disabled={send.isPending || chosen.length === 0 || reason.trim().length < 3} onClick={() => act("returns", { reason: reason.trim(), items: chosen.map(([sale_item_id, quantity]) => ({ sale_item_id, quantity })) })}>
                {t("sales.confirmReturn")}
              </Button>
            ) : null}
            {mode === "cancel" ? (
              <Button className="bg-danger text-white hover:bg-danger/90" disabled={send.isPending || reason.trim().length < 3} onClick={() => act("cancel", { reason: reason.trim() })}>
                {t("sales.confirmCancel")}
              </Button>
            ) : null}
            {mode === "pay" ? (
              <Button disabled={send.isPending || !isPositive(amount) || compare(amount, sale.balance_due) > 0} onClick={() => act("payments", { amount, method })}>
                {t("sales.confirmCollect")}
              </Button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

export function SalesPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"" | "unpaid" | "cancelled">("");
  const [open, setOpen] = useState<Sale | null>(null);
  const list = useList<Sale>("/sales", { page, page_size: 15, q, unpaid_only: filter === "unpaid" ? true : undefined, status: filter === "cancelled" ? "cancelled" : undefined });
  const columns: Column<Sale>[] = [
    { key: "number", header: t("fields.number"), render: (r) => <bdi className="font-mono font-medium">{r.number}</bdi> },
    { key: "date", header: t("fields.date"), render: (r) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.created_at, i18n.language)}</span> },
    { key: "customer", header: t("sales.customer"), render: (r) => r.customer_name ?? <span className="text-muted-foreground">{t("pos.walkIn")}</span> },
    { key: "status", header: t("org.status"), render: (r) => <Badge tone={TONE[r.payment_status]}>{t(`sales.status.${r.payment_status}`)}</Badge> },
    { key: "total", header: t("fields.total"), align: "end", render: (r) => <bdi className="tabular-nums">{money(r.total)}</bdi> },
    { key: "due", header: t("fields.balanceDue"), align: "end", render: (r) => <bdi className="tabular-nums text-muted-foreground">{money(r.balance_due)}</bdi> },
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("sales.title")} subtitle={t("sales.subtitle")}>
        <ExportButton path="/sales/export" params={{ q, unpaid_only: filter === "unpaid" ? true : undefined, status: filter === "cancelled" ? "cancelled" : undefined }} filename="invoices.csv" />
      </PageHeader>
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b p-3">
          <SearchInput placeholder={t("sales.search")} onSearch={(v) => { setQ(v); setPage(1); }} />
          <select aria-label={t("org.status")} value={filter} onChange={(e) => { setFilter(e.target.value as typeof filter); setPage(1); }} className="h-10 rounded-md border bg-card px-3 text-sm">
            <option value="">{t("common.allStatuses")}</option>
            <option value="unpaid">{t("sales.unpaidOnly")}</option>
            <option value="cancelled">{t("sales.status.cancelled")}</option>
          </select>
        </div>
        <DataTable query={list} columns={columns} rowKey={(r) => r.id} empty={t("sales.empty")} onRowClick={setOpen} page={page} pageSize={15} onPage={setPage} minWidth="46rem" />
      </Card>
      <Modal open={open !== null} title={open ? `${t("sales.invoice")} ${open.number}` : ""} closeLabel={t("org.close")} onClose={() => setOpen(null)}>
        {open ? <Detail key={open.id} id={open.id} onClose={() => setOpen(null)} /> : null}
      </Modal>
    </section>
  );
}
