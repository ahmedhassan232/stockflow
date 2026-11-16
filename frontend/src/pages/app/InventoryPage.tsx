import { ArrowLeftRight, History, SlidersHorizontal, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ExportButton } from "@/components/common/ExportButton";
import { DataTable, ErrorAlert, FormActions, PageHeader, SearchInput, Stat, Tabs, type Column } from "@/components/common/data";
import { ProductPicker, decimalInput, useMoney } from "@/components/common/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { useCan } from "@/features/auth/store";
import { newKey, useGet, useList, useSend } from "@/features/data/api";
import type { Balance, Movement, Product, WarehouseItem } from "@/features/data/types";
import { isPositive } from "@/utils/decimal";
import { formatDateTime, formatQty } from "@/utils/format";

const PAGE_SIZE = 15;
type BalanceRow = Balance & { average_cost: string; stock_value: string };

function useWarehouses() {
  return useList<WarehouseItem>("/warehouses", { page_size: 100, is_active: true }).data?.items ?? [];
}

function AdjustForm({ preset, onDone }: { preset: BalanceRow | null; onDone: () => void }) {
  const { t } = useTranslation();
  const warehouses = useWarehouses();
  const send = useSend(["inventory", "products", "reports"]);
  const [key] = useState(newKey); // one key per opened form: double-click cannot adjust twice
  const [warehouse, setWarehouse] = useState(preset?.warehouse_id ?? "");
  const [product, setProduct] = useState<{ id: string; name: string } | null>(preset ? { id: preset.product_id, name: preset.product_name } : null);
  const [direction, setDirection] = useState<"in" | "out">("in");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const warehouseId = warehouse || warehouses[0]?.id || "";
  const valid = !!warehouseId && !!product && isPositive(quantity) && reason.trim().length >= 3;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid || !product) return;
    send.mutate(
      { path: "/inventory/adjustments", idempotencyKey: key, body: { warehouse_id: warehouseId, product_id: product.id, direction, quantity, reason: reason.trim() } },
      { onSuccess: onDone },
    );
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      <SelectField label={t("inventory.warehouse")} value={warehouseId} onChange={(e) => setWarehouse(e.target.value)}>
        {warehouses.map((w) => (
          <option key={w.id} value={w.id}>{w.name}</option>
        ))}
      </SelectField>
      {product ? (
        <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
          <span className="font-medium">{product.name}</span>
          {preset ? null : (
            <Button variant="ghost" size="sm" onClick={() => setProduct(null)}>{t("common.change")}</Button>
          )}
        </div>
      ) : (
        <ProductPicker trackedOnly onPick={(p: Product) => setProduct({ id: p.id, name: p.name })} />
      )}
      <div className="grid grid-cols-2 gap-4">
        <SelectField label={t("inventory.direction")} value={direction} onChange={(e) => setDirection(e.target.value as "in" | "out")}>
          <option value="in">{t("inventory.increase")}</option>
          <option value="out">{t("inventory.decrease")}</option>
        </SelectField>
        <TextField label={t("fields.quantity")} dir="ltr" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
      </div>
      <TextField label={t("inventory.reason")} hint={t("inventory.reasonHint")} value={reason} onChange={(e) => setReason(e.target.value)} />
      <FormActions onCancel={onDone} pending={send.isPending} disabled={!valid} submitLabel={t("inventory.adjust")} />
    </form>
  );
}

function TransferForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const warehouses = useWarehouses();
  const send = useSend(["inventory", "reports"]);
  const [key] = useState(newKey);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [lines, setLines] = useState<{ id: string; name: string; quantity: string }[]>([]);
  const valid = !!from && !!to && from !== to && lines.length > 0 && lines.every((l) => isPositive(l.quantity));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    send.mutate(
      { path: "/inventory/transfers", idempotencyKey: key, body: { from_warehouse_id: from, to_warehouse_id: to, items: lines.map((l) => ({ product_id: l.id, quantity: l.quantity })) } },
      { onSuccess: onDone },
    );
  };
  const options = (
    <>
      <option value="" disabled />
      {warehouses.map((w) => (
        <option key={w.id} value={w.id}>{w.name}</option>
      ))}
    </>
  );
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      {warehouses.length < 2 ? <p className="text-sm text-warning">{t("inventory.needTwoWarehouses")}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label={t("inventory.from")} value={from} onChange={(e) => setFrom(e.target.value)}>{options}</SelectField>
        <SelectField label={t("inventory.to")} value={to} onChange={(e) => setTo(e.target.value)} error={from && from === to ? t("inventory.sameWarehouse") : undefined}>{options}</SelectField>
      </div>
      <ProductPicker trackedOnly exclude={lines.map((l) => l.id)} onPick={(p) => setLines((ls) => [...ls, { id: p.id, name: p.name, quantity: "1" }])} />
      {lines.length ? (
        <ul className="divide-y rounded-md border text-sm">
          {lines.map((line) => (
            <li key={line.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="min-w-0 flex-1 truncate">{line.name}</span>
              <input
                aria-label={t("fields.quantity")}
                dir="ltr"
                inputMode="decimal"
                className={decimalInput}
                aria-invalid={!isPositive(line.quantity)}
                value={line.quantity}
                onChange={(e) => setLines((ls) => ls.map((l) => (l.id === line.id ? { ...l, quantity: e.target.value } : l)))}
              />
              <Button variant="ghost" size="icon" className="size-9" aria-label={t("common.delete")} onClick={() => setLines((ls) => ls.filter((l) => l.id !== line.id))}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <FormActions onCancel={onDone} pending={send.isPending} disabled={!valid} submitLabel={t("inventory.transfer")} />
    </form>
  );
}

function MinimumForm({ row, onDone }: { row: BalanceRow; onDone: () => void }) {
  const { t } = useTranslation();
  const send = useSend(["inventory", "reports"]);
  const [level, setLevel] = useState(row.minimum_stock_level);
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate({ method: "put", path: "/inventory/minimum-level", body: { warehouse_id: row.warehouse_id, product_id: row.product_id, minimum_stock_level: level || "0" } }, { onSuccess: onDone });
      }}
    >
      <ErrorAlert error={send.error} />
      <p className="text-sm text-muted-foreground">{row.product_name} · {row.warehouse_name}</p>
      <TextField label={t("inventory.minimum")} hint={t("inventory.minimumHint")} dir="ltr" inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} />
      <FormActions onCancel={onDone} pending={send.isPending} />
    </form>
  );
}

function MovementsView({ row }: { row: BalanceRow }) {
  const { t, i18n } = useTranslation();
  const [page, setPage] = useState(1);
  const list = useList<Movement>("/inventory/movements", { product_id: row.product_id, warehouse_id: row.warehouse_id, page, page_size: 10 });
  const columns: Column<Movement>[] = [
    { key: "date", header: t("fields.date"), render: (m) => <span className="whitespace-nowrap">{formatDateTime(m.created_at, i18n.language)}</span> },
    { key: "type", header: t("inventory.movementType"), render: (m) => t(`movement.${m.movement_type}`) },
    {
      key: "qty",
      header: t("fields.quantity"),
      align: "end",
      render: (m) =>
        Number(m.quantity_in) > 0 ? (
          <bdi className="tabular-nums text-success">+{formatQty(m.quantity_in, i18n.language)}</bdi>
        ) : (
          <bdi className="tabular-nums text-danger">−{formatQty(m.quantity_out, i18n.language)}</bdi>
        ),
    },
    { key: "after", header: t("inventory.balanceAfter"), align: "end", render: (m) => <bdi className="tabular-nums">{formatQty(m.balance_after, i18n.language)}</bdi> },
    { key: "reason", header: t("inventory.reason"), render: (m) => <span className="text-muted-foreground">{m.reason ?? "—"}</span> },
  ];
  return (
    <div className="-m-5">
      <p className="border-b px-5 py-3 text-sm text-muted-foreground">{row.product_name} · {row.warehouse_name} · {t("inventory.immutable")}</p>
      <DataTable query={list} columns={columns} rowKey={(m) => m.id} empty={t("inventory.noMovements")} page={page} pageSize={10} onPage={setPage} minWidth="34rem" />
    </div>
  );
}

export function InventoryPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const canAdjust = useCan("inventory.adjust");
  const canTransfer = useCan("inventory.transfer");
  const canValue = useCan("reports.inventory.view");
  const warehouses = useWarehouses();
  const [tab, setTab] = useState<"all" | "low">("all");
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [modal, setModal] = useState<{ kind: "adjust" | "transfer" | "minimum" | "movements"; row: BalanceRow | null } | null>(null);
  const list = useList<BalanceRow>(tab === "low" ? "/inventory/low-stock" : "/inventory", { page, page_size: PAGE_SIZE, q: tab === "all" ? q : undefined, warehouse_id: warehouse });
  const valuation = useGet<{ total_value: string }>("/inventory/valuation", undefined, canValue);
  const low = useList<BalanceRow>("/inventory/low-stock", { page_size: 1 });

  const columns: Column<BalanceRow>[] = [
    {
      key: "product",
      header: t("fields.product"),
      render: (r) => (
        <>
          <span className="font-medium">{r.product_name}</span>
          <bdi className="block font-mono text-xs text-muted-foreground">{r.sku}</bdi>
        </>
      ),
    },
    { key: "warehouse", header: t("inventory.warehouse"), render: (r) => r.warehouse_name },
    {
      key: "qty",
      header: t("inventory.onHand"),
      align: "end",
      render: (r) => (
        <span className="inline-flex items-center gap-2">
          {r.is_low ? <Badge tone="danger">{t("inventory.low")}</Badge> : null}
          <bdi className="font-semibold tabular-nums">{formatQty(r.quantity, i18n.language)}</bdi>
        </span>
      ),
    },
    { key: "min", header: t("inventory.minimum"), align: "end", render: (r) => <bdi className="tabular-nums text-muted-foreground">{formatQty(r.minimum_stock_level, i18n.language)}</bdi> },
    ...(canValue ? [{ key: "value", header: t("inventory.value"), align: "end" as const, render: (r: BalanceRow) => <bdi className="tabular-nums">{money(r.stock_value)}</bdi> }] : []),
    {
      key: "actions",
      header: t("org.actions"),
      align: "end",
      className: "whitespace-nowrap py-2",
      render: (r) => (
        <>
          <Button variant="ghost" size="sm" onClick={() => setModal({ kind: "movements", row: r })}>
            <History />
            {t("inventory.movements")}
          </Button>
          {canAdjust ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setModal({ kind: "adjust", row: r })}>
                <SlidersHorizontal />
                {t("inventory.adjust")}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setModal({ kind: "minimum", row: r })}>
                {t("inventory.setMinimum")}
              </Button>
            </>
          ) : null}
        </>
      ),
    },
  ];
  const close = () => setModal(null);
  const titles = { adjust: t("inventory.adjustTitle"), transfer: t("inventory.transferTitle"), minimum: t("inventory.minimum"), movements: t("inventory.movements") };

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("inventory.title")} subtitle={t("inventory.subtitle")}>
        <ExportButton path="/inventory/export" params={{ warehouse_id: warehouse, low_only: tab === "low" ? true : undefined }} filename="stock.csv" />
        {canTransfer ? (
          <Button variant="outline" onClick={() => setModal({ kind: "transfer", row: null })}>
            <ArrowLeftRight />
            {t("inventory.transfer")}
          </Button>
        ) : null}
        {canAdjust ? (
          <Button onClick={() => setModal({ kind: "adjust", row: null })}>
            <SlidersHorizontal />
            {t("inventory.adjust")}
          </Button>
        ) : null}
      </PageHeader>

      <div className="mb-5 grid gap-4 sm:grid-cols-2">
        {canValue ? <Stat label={t("inventory.totalValue")} value={<bdi>{money(valuation.data?.total_value)}</bdi>} hint={t("inventory.valuationMethod")} /> : null}
        <Stat label={t("inventory.lowCount")} value={low.data?.total ?? "—"} tone={low.data?.total ? "danger" : undefined} />
      </div>

      <Tabs tabs={[{ key: "all", label: t("inventory.allStock") }, { key: "low", label: t("inventory.lowStock") }]} value={tab} onChange={(k) => { setTab(k); setPage(1); }} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b p-3">
          {tab === "all" ? <SearchInput placeholder={t("org.search")} onSearch={(v) => { setQ(v); setPage(1); }} /> : null}
          <select aria-label={t("inventory.warehouse")} value={warehouse} onChange={(e) => { setWarehouse(e.target.value); setPage(1); }} className="h-10 rounded-md border bg-card px-3 text-sm">
            <option value="">{t("inventory.allWarehouses")}</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
        </div>
        <DataTable query={list} columns={columns} rowKey={(r) => `${r.warehouse_id}:${r.product_id}`} empty={t(tab === "low" ? "inventory.noLow" : "inventory.empty")} page={page} pageSize={PAGE_SIZE} onPage={setPage} minWidth="52rem" />
      </Card>

      <Modal open={modal !== null} title={modal ? titles[modal.kind] : ""} closeLabel={t("org.close")} onClose={close} wide={modal?.kind === "movements" || modal?.kind === "transfer"}>
        {modal?.kind === "adjust" ? <AdjustForm preset={modal.row} onDone={close} /> : null}
        {modal?.kind === "transfer" ? <TransferForm onDone={close} /> : null}
        {modal?.kind === "minimum" && modal.row ? <MinimumForm row={modal.row} onDone={close} /> : null}
        {modal?.kind === "movements" && modal.row ? <MovementsView row={modal.row} /> : null}
      </Modal>
    </section>
  );
}
