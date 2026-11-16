import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DataTable, ErrorAlert, PageHeader, SearchInput, type Column } from "@/components/common/data";
import { LookupSelect, ProductPicker, decimalInput, useMoney, useWarehouseChoice } from "@/components/common/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/store";
import { newKey, useGet, useList, useSend } from "@/features/data/api";
import { PAYMENT_METHODS, type Purchase } from "@/features/data/types";
import { compare, isPositive, linePreview, parse, toFixed } from "@/utils/decimal";
import { formatDateTime, formatQty } from "@/utils/format";

const STALE = ["purchases", "inventory", "products", "reports", "notifications"];
const TONE = { draft: "neutral", ordered: "warning", partially_received: "warning", received: "success", cancelled: "danger" } as const;
const STATUSES = ["draft", "ordered", "partially_received", "received", "cancelled"] as const;

interface Line {
  id: string;
  name: string;
  quantity: string;
  unit_cost: string;
  tax_rate: string;
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const money = useMoney();
  const send = useSend(STALE);
  const [key] = useState(newKey);
  const warehouse = useWarehouseChoice();
  const [supplier, setSupplier] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [notes, setNotes] = useState("");
  const update = (id: string, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const total = lines.reduce((sum, l) => sum + linePreview(l.quantity, l.unit_cost, l.tax_rate).total, 0n);
  const valid = !!supplier && !!warehouse.value && lines.length > 0 && lines.every((l) => isPositive(l.quantity) && /^\d+(\.\d{1,4})?$/.test(l.unit_cost) && Number(l.tax_rate || 0) <= 100);

  const submit = (status: "draft" | "ordered") => (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    send.mutate(
      {
        path: "/purchases",
        idempotencyKey: key,
        body: {
          supplier_id: supplier,
          warehouse_id: warehouse.value,
          status,
          notes: notes.trim() || null,
          items: lines.map((l) => ({ product_id: l.id, quantity: l.quantity, unit_cost: l.unit_cost, tax_rate: l.tax_rate || "0" })),
        },
      },
      { onSuccess: onDone },
    );
  };

  return (
    <form onSubmit={submit("ordered")} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <LookupSelect path="/suppliers" label={t("purchases.supplier")} value={supplier} onChange={setSupplier} />
        <SelectField label={t("inventory.warehouse")} value={warehouse.value} onChange={(e) => warehouse.set(e.target.value)}>
          {warehouse.warehouses.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </SelectField>
      </div>
      <ProductPicker trackedOnly exclude={lines.map((l) => l.id)} onPick={(p) => setLines((ls) => [...ls, { id: p.id, name: p.name, quantity: "1", unit_cost: p.purchase_price, tax_rate: p.tax_rate }])} />
      {lines.length ? (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="bg-muted/60 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-start font-medium">{t("fields.product")}</th>
                <th className="px-3 py-2 text-start font-medium">{t("fields.quantity")}</th>
                <th className="px-3 py-2 text-start font-medium">{t("purchases.unitCost")}</th>
                <th className="px-3 py-2 text-start font-medium">{t("products.taxRate")}</th>
                <th className="px-3 py-2 text-end font-medium">{t("fields.total")}</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y">
              {lines.map((l) => (
                <tr key={l.id}>
                  <td className="px-3 py-2">{l.name}</td>
                  <td className="px-3 py-2"><input aria-label={t("fields.quantity")} dir="ltr" inputMode="decimal" className={decimalInput} aria-invalid={!isPositive(l.quantity)} value={l.quantity} onChange={(e) => update(l.id, { quantity: e.target.value })} /></td>
                  <td className="px-3 py-2"><input aria-label={t("purchases.unitCost")} dir="ltr" inputMode="decimal" className={decimalInput} value={l.unit_cost} onChange={(e) => update(l.id, { unit_cost: e.target.value })} /></td>
                  <td className="px-3 py-2"><input aria-label={t("products.taxRate")} dir="ltr" inputMode="decimal" className={`${decimalInput} w-16`} value={l.tax_rate} onChange={(e) => update(l.id, { tax_rate: e.target.value })} /></td>
                  <td className="px-3 py-2 text-end"><bdi className="tabular-nums">{money(toFixed(linePreview(l.quantity, l.unit_cost, l.tax_rate).total))}</bdi></td>
                  <td className="px-1">
                    <Button variant="ghost" size="icon" className="size-9" aria-label={t("common.delete")} onClick={() => setLines((ls) => ls.filter((x) => x.id !== l.id))}>
                      <Trash2 />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">{t("purchases.addLines")}</p>
      )}
      <TextField label={t("fields.notes")} value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          {t("purchases.estimatedTotal")}: <bdi className="text-lg font-bold tabular-nums">{money(toFixed(total))}</bdi>
        </p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onDone}>{t("org.cancel")}</Button>
          <Button variant="outline" disabled={!valid || send.isPending} onClick={submit("draft")}>{t("purchases.saveDraft")}</Button>
          <Button type="submit" disabled={!valid || send.isPending}>{t("purchases.placeOrder")}</Button>
        </div>
      </div>
    </form>
  );
}

function Detail({ id, onClose }: { id: string; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const query = useGet<Purchase>(`/purchases/${id}`);
  const send = useSend<Purchase>(STALE);
  const [key, setKey] = useState(newKey);
  const [mode, setMode] = useState<"view" | "receive" | "return" | "pay">("view");
  const [qty, setQty] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<string>("cash");
  const can = { receive: useCan("purchases.receive"), cancel: useCan("purchases.cancel"), create: useCan("purchases.create"), pay: useCan("payments.manage") };
  const po = query.data;
  if (query.isPending) return <Skeleton className="h-48" />;
  if (!po) return <ErrorAlert error={query.error} />;

  const done = () => {
    setMode("view");
    setQty({});
    setReason("");
    setAmount("");
    setKey(newKey());
  };
  const act = (path: string, body?: unknown) => send.mutate({ path: `/purchases/${id}/${path}`, body, idempotencyKey: body ? key : undefined }, { onSuccess: done });
  const start = (next: typeof mode) => {
    send.reset();
    setMode(next);
    if (next === "receive") setQty(Object.fromEntries((po.items ?? []).map((i) => [i.id, toFixed(parse(i.quantity) - parse(i.received_quantity), 3)])));
    if (next === "pay") setAmount(po.balance_due);
  };
  const chosen = Object.entries(qty).filter(([, v]) => isPositive(v));
  const receivable = po.status === "ordered" || po.status === "partially_received";
  const returnable = po.status === "received" || po.status === "partially_received";
  const payable = !["draft", "cancelled"].includes(po.status) && isPositive(po.balance_due);
  const editing = mode === "receive" || mode === "return";

  return (
    <div className="space-y-4">
      <ErrorAlert error={send.error} />
      <dl className="grid gap-3 text-sm sm:grid-cols-4">
        {[
          [t("purchases.supplier"), po.supplier_name],
          [t("inventory.warehouse"), po.warehouse_name],
          [t("fields.date"), formatDateTime(po.created_at, i18n.language)],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
        <div>
          <dt className="text-xs text-muted-foreground">{t("org.status")}</dt>
          <dd><Badge tone={TONE[po.status]}>{t(`purchases.status.${po.status}`)}</Badge></dd>
        </div>
      </dl>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[34rem] text-sm">
          <thead className="bg-muted/60 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-start font-medium">{t("fields.product")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("purchases.ordered")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("purchases.received")}</th>
              <th className="px-3 py-2 text-end font-medium">{t("purchases.unitCost")}</th>
              <th className="px-3 py-2 text-end font-medium">{editing ? t(mode === "receive" ? "purchases.receiveNow" : "purchases.returnNow") : t("fields.total")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {(po.items ?? []).map((i) => (
              <tr key={i.id}>
                <td className="px-3 py-2">{i.product_name}</td>
                <td className="px-3 py-2 text-end tabular-nums">{formatQty(i.quantity, i18n.language)}</td>
                <td className="px-3 py-2 text-end tabular-nums">
                  {formatQty(i.received_quantity, i18n.language)}
                  {isPositive(i.returned_quantity) ? <span className="text-danger"> (−{formatQty(i.returned_quantity, i18n.language)})</span> : null}
                </td>
                <td className="px-3 py-2 text-end"><bdi className="tabular-nums">{money(i.unit_cost)}</bdi></td>
                <td className="px-3 py-2 text-end">
                  {editing ? (
                    <input aria-label={i.product_name} dir="ltr" inputMode="decimal" className={decimalInput} value={qty[i.id] ?? ""} onChange={(e) => setQty((q) => ({ ...q, [i.id]: e.target.value }))} />
                  ) : (
                    <bdi className="tabular-nums">{money(i.line_total)}</bdi>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="ms-auto grid max-w-xs grid-cols-2 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t("fields.tax")}</dt>
        <dd className="text-end"><bdi className="tabular-nums">{money(po.tax_amount)}</bdi></dd>
        <dt className="font-semibold">{t("fields.total")}</dt>
        <dd className="text-end font-semibold"><bdi className="tabular-nums">{money(po.total)}</bdi></dd>
        <dt className="text-muted-foreground">{t("fields.paid")}</dt>
        <dd className="text-end"><bdi className="tabular-nums">{money(po.paid_amount)}</bdi></dd>
        <dt className="text-muted-foreground">{t("fields.balanceDue")}</dt>
        <dd className="text-end"><bdi className="tabular-nums">{money(po.balance_due)}</bdi></dd>
      </dl>

      {mode === "return" ? <TextField label={t("inventory.reason")} value={reason} onChange={(e) => setReason(e.target.value)} /> : null}
      {mode === "pay" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={t("fields.amount")} dir="ltr" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={compare(amount || "0", po.balance_due) > 0 ? t("errors.OVERPAYMENT") : undefined} />
          <SelectField label={t("fields.method")} value={method} onChange={(e) => setMethod(e.target.value)}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>{t(`method.${m}`)}</option>
            ))}
          </SelectField>
        </div>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
        {mode === "view" ? (
          <>
            <Button variant="outline" onClick={onClose}>{t("org.close")}</Button>
            {po.status === "draft" && can.create ? <Button disabled={send.isPending} onClick={() => act("confirm")}>{t("purchases.placeOrder")}</Button> : null}
            {(po.status === "draft" || po.status === "ordered") && can.cancel ? <Button variant="outline" className="text-danger" disabled={send.isPending} onClick={() => act("cancel")}>{t("purchases.cancelOrder")}</Button> : null}
            {returnable && can.cancel ? <Button variant="outline" onClick={() => start("return")}>{t("purchases.returnGoods")}</Button> : null}
            {payable && can.pay ? <Button variant="outline" onClick={() => start("pay")}>{t("purchases.pay")}</Button> : null}
            {receivable && can.receive ? <Button onClick={() => start("receive")}>{t("purchases.receive")}</Button> : null}
          </>
        ) : (
          <>
            <Button variant="outline" onClick={done}>{t("org.cancel")}</Button>
            {mode === "receive" ? <Button disabled={send.isPending || chosen.length === 0} onClick={() => act("receive", { items: chosen.map(([item_id, quantity]) => ({ item_id, quantity })) })}>{t("purchases.confirmReceive")}</Button> : null}
            {mode === "return" ? <Button disabled={send.isPending || chosen.length === 0 || reason.trim().length < 3} onClick={() => act("returns", { reason: reason.trim(), items: chosen.map(([item_id, quantity]) => ({ item_id, quantity })) })}>{t("purchases.confirmReturn")}</Button> : null}
            {mode === "pay" ? <Button disabled={send.isPending || !isPositive(amount) || compare(amount, po.balance_due) > 0} onClick={() => act("payments", { amount, method })}>{t("purchases.confirmPay")}</Button> : null}
          </>
        )}
      </div>
    </div>
  );
}

export function PurchasesPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const canCreate = useCan("purchases.create");
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<Purchase | null>(null);
  const list = useList<Purchase>("/purchases", { page, page_size: 15, q, status });
  const columns: Column<Purchase>[] = [
    { key: "number", header: t("fields.number"), render: (r) => <bdi className="font-mono font-medium">{r.number}</bdi> },
    { key: "supplier", header: t("purchases.supplier"), render: (r) => r.supplier_name },
    { key: "date", header: t("fields.date"), render: (r) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.created_at, i18n.language)}</span> },
    { key: "status", header: t("org.status"), render: (r) => <Badge tone={TONE[r.status]}>{t(`purchases.status.${r.status}`)}</Badge> },
    { key: "total", header: t("fields.total"), align: "end", render: (r) => <bdi className="tabular-nums">{money(r.total)}</bdi> },
    { key: "due", header: t("fields.balanceDue"), align: "end", render: (r) => <bdi className="tabular-nums text-muted-foreground">{money(r.balance_due)}</bdi> },
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("purchases.title")} subtitle={t("purchases.subtitle")}>
        {canCreate ? (
          <Button onClick={() => setCreating(true)}>
            <Plus />
            {t("purchases.add")}
          </Button>
        ) : null}
      </PageHeader>
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b p-3">
          <SearchInput placeholder={t("purchases.search")} onSearch={(v) => { setQ(v); setPage(1); }} />
          <select aria-label={t("org.status")} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-10 rounded-md border bg-card px-3 text-sm">
            <option value="">{t("common.allStatuses")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{t(`purchases.status.${s}`)}</option>
            ))}
          </select>
        </div>
        <DataTable query={list} columns={columns} rowKey={(r) => r.id} empty={t("purchases.empty")} onRowClick={setOpen} page={page} pageSize={15} onPage={setPage} minWidth="46rem" />
      </Card>
      <Modal open={creating} title={t("purchases.add")} closeLabel={t("org.close")} onClose={() => setCreating(false)} wide>
        {creating ? <CreateForm onDone={() => setCreating(false)} /> : null}
      </Modal>
      <Modal open={open !== null} title={open?.number ?? ""} closeLabel={t("org.close")} onClose={() => setOpen(null)} wide>
        {open ? <Detail key={open.id} id={open.id} onClose={() => setOpen(null)} /> : null}
      </Modal>
    </section>
  );
}
