import { Minus, Plus, ShoppingCart, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorAlert, PageHeader } from "@/components/common/data";
import { LookupSelect, decimalInput, useMoney, useWarehouseChoice } from "@/components/common/pickers";
import { Receipt } from "@/components/common/Receipt";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/store";
import { newKey, useGet, useList, useSend } from "@/features/data/api";
import { PAYMENT_METHODS, type Product, type Sale } from "@/features/data/types";
import { ApiError } from "@/services/api";
import { isPositive, linePreview, parse, toFixed } from "@/utils/decimal";
import { errorMessage } from "@/utils/errors";

interface CartLine {
  product: Product;
  quantity: string;
  discount: string;
}

export function PosPage() {
  const { t } = useTranslation();
  const money = useMoney();
  const warehouse = useWarehouseChoice();
  const searchRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customer, setCustomer] = useState("");
  const [method, setMethod] = useState<string>("cash");
  const [tendered, setTendered] = useState("");
  const [receipt, setReceipt] = useState<Sale | null>(null);
  // One idempotency key per cart. It changes only when the cart changes or the sale
  // succeeds, so a double click / network retry can never create a second invoice.
  const [key, setKey] = useState(newKey);
  const checkout = useSend<Sale>(["sales", "inventory", "products", "reports", "notifications"]);
  const products = useList<Product>("/products", { q, page_size: 24, is_active: true, sort: "name" });
  const canSeeSettings = useCan("settings.view");
  const settings = useGet<{ invoice_footer: string | null }>("/settings", undefined, receipt !== null && canSeeSettings);

  const touch = () => {
    setKey(newKey());
    checkout.reset();
  };
  const add = (product: Product) => {
    touch();
    setCart((lines) => {
      const existing = lines.find((l) => l.product.id === product.id);
      if (!existing) return [...lines, { product, quantity: "1", discount: "" }];
      return lines.map((l) => (l === existing ? { ...l, quantity: toFixed(parse(l.quantity) + parse("1"), 3).replace(/\.?0+$/, "") } : l));
    });
  };
  const update = (id: string, patch: Partial<CartLine>) => {
    touch();
    setCart((lines) => lines.map((l) => (l.product.id === id ? { ...l, ...patch } : l)));
  };
  const step = (line: CartLine, delta: number) => {
    const next = parse(line.quantity) + parse(String(delta));
    if (next <= 0n) {
      touch();
      setCart((lines) => lines.filter((l) => l !== line));
    } else update(line.product.id, { quantity: toFixed(next, 3).replace(/\.?0+$/, "") });
  };

  const totals = useMemo(() => {
    let gross = 0n, discount = 0n, tax = 0n, total = 0n;
    for (const l of cart) {
      const p = linePreview(l.quantity, l.product.selling_price, l.product.tax_rate, l.discount || "0");
      gross += p.gross; discount += p.discount; tax += p.tax; total += p.total;
    }
    return { gross, discount, tax, total };
  }, [cart]);

  const paid = tendered.trim() === "" ? totals.total : parse(tendered);
  const change = paid - totals.total;
  const linesValid = cart.length > 0 && cart.every((l) => isPositive(l.quantity) && linePreview(l.quantity, l.product.selling_price, l.product.tax_rate, l.discount || "0").total >= 0n && parse(l.discount || "0") <= linePreview(l.quantity, l.product.selling_price, "0").gross);
  const needsCustomer = change < 0n && !customer;
  const overpaidNonCash = change > 0n && method !== "cash";
  const canPay = linesValid && !!warehouse.value && !needsCustomer && !overpaidNonCash && paid >= 0n;

  const onScan = () => {
    // Barcode scanners type the code and press Enter: add the exact match immediately.
    const code = term.trim();
    if (!code) return;
    const hit = products.data?.items.find((p) => p.barcode === code || p.sku === code.toUpperCase());
    if (hit) {
      add(hit);
      setTerm("");
      setQ("");
    } else setQ(code);
  };

  const pay = () => {
    if (!canPay) return;
    checkout.mutate(
      {
        path: "/sales",
        idempotencyKey: key,
        body: {
          warehouse_id: warehouse.value,
          customer_id: customer || null,
          items: cart.map((l) => ({ product_id: l.product.id, quantity: l.quantity, discount_amount: l.discount || "0" })),
          payments: paid > 0n ? [{ method, amount: toFixed(paid) }] : [],
        },
      },
      {
        onSuccess: (sale) => {
          setReceipt(sale);
          setCart([]);
          setTendered("");
          setCustomer("");
          setKey(newKey());
        },
      },
    );
  };

  const stockDetail = checkout.error instanceof ApiError && checkout.error.code === "INSUFFICIENT_STOCK" ? (checkout.error.details as { product_id?: string; available?: string } | undefined) : undefined;
  const shortName = cart.find((l) => l.product.id === stockDetail?.product_id)?.product.name;

  return (
    <section className="mx-auto max-w-7xl">
      <PageHeader title={t("pos.title")} subtitle={t("pos.subtitle")}>
        <select aria-label={t("inventory.warehouse")} value={warehouse.value} onChange={(e) => { warehouse.set(e.target.value); touch(); }} className="h-10 rounded-md border bg-card px-3 text-sm">
          {warehouse.warehouses.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-[1fr_24rem]">
        <Card className="p-4">
          <form onSubmit={(e) => { e.preventDefault(); onScan(); }}>
            <label className="sr-only" htmlFor="pos-search">{t("pos.search")}</label>
            <input
              id="pos-search"
              ref={searchRef}
              autoFocus
              value={term}
              onChange={(e) => { setTerm(e.target.value); if (e.target.value === "") setQ(""); }}
              placeholder={t("pos.search")}
              className="h-11 w-full rounded-md border bg-card px-3 text-sm placeholder:text-muted-foreground"
            />
          </form>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            {products.isPending ? (
              [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24" />)
            ) : products.isError ? (
              <div className="col-span-full"><ErrorAlert error={products.error} /></div>
            ) : products.data.items.length === 0 ? (
              <p className="col-span-full py-10 text-center text-sm text-muted-foreground">{t("products.noMatch")}</p>
            ) : (
              products.data.items.map((p) => (
                <button key={p.id} type="button" onClick={() => add(p)} className="flex min-h-24 flex-col justify-between rounded-md border bg-card p-3 text-start transition-colors hover:border-secondary hover:bg-accent">
                  <span className="line-clamp-2 text-sm font-medium">{p.name}</span>
                  <span className="mt-2 flex items-end justify-between gap-2">
                    <bdi className="font-mono text-[11px] text-muted-foreground">{p.sku}</bdi>
                    <bdi className="text-sm font-bold tabular-nums text-secondary">{money(p.selling_price)}</bdi>
                  </span>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card className="flex flex-col lg:sticky lg:top-20 lg:max-h-[calc(100dvh-7rem)]">
          <h2 className="flex items-center gap-2 border-b px-4 py-3 font-semibold">
            <ShoppingCart className="size-4" aria-hidden="true" />
            {t("pos.cart")} {cart.length ? <span className="text-muted-foreground">({cart.length})</span> : null}
          </h2>
          <ul className="flex-1 divide-y overflow-y-auto">
            {cart.length === 0 ? (
              <li className="p-8 text-center text-sm text-muted-foreground">{t("pos.emptyCart")}</li>
            ) : (
              cart.map((line) => {
                const preview = linePreview(line.quantity, line.product.selling_price, line.product.tax_rate, line.discount || "0");
                return (
                  <li key={line.product.id} className="space-y-2 px-4 py-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium">{line.product.name}</span>
                      <bdi className="font-semibold tabular-nums">{money(toFixed(preview.total))}</bdi>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button variant="outline" size="icon" className="size-9" aria-label={t("pos.less")} onClick={() => step(line, -1)}>
                        <Minus />
                      </Button>
                      <input aria-label={t("fields.quantity")} dir="ltr" inputMode="decimal" className={`${decimalInput} w-16 text-center`} aria-invalid={!isPositive(line.quantity)} value={line.quantity} onChange={(e) => update(line.product.id, { quantity: e.target.value })} />
                      <Button variant="outline" size="icon" className="size-9" aria-label={t("pos.more")} onClick={() => step(line, 1)}>
                        <Plus />
                      </Button>
                      <input aria-label={t("fields.discount")} placeholder={t("fields.discount")} dir="ltr" inputMode="decimal" className={`${decimalInput} ms-auto w-20`} value={line.discount} onChange={(e) => update(line.product.id, { discount: e.target.value })} />
                      <Button variant="ghost" size="icon" className="size-9 text-danger" aria-label={t("common.delete")} onClick={() => step(line, -1e9)}>
                        <Trash2 />
                      </Button>
                    </div>
                  </li>
                );
              })
            )}
          </ul>

          <div className="space-y-3 border-t p-4">
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between"><dt className="text-muted-foreground">{t("fields.subtotal")}</dt><dd><bdi className="tabular-nums">{money(toFixed(totals.gross))}</bdi></dd></div>
              {totals.discount > 0n ? <div className="flex justify-between"><dt className="text-muted-foreground">{t("fields.discount")}</dt><dd><bdi className="tabular-nums">−{money(toFixed(totals.discount))}</bdi></dd></div> : null}
              <div className="flex justify-between"><dt className="text-muted-foreground">{t("fields.tax")}</dt><dd><bdi className="tabular-nums">{money(toFixed(totals.tax))}</bdi></dd></div>
              <div className="flex justify-between border-t pt-2 text-lg font-bold"><dt>{t("fields.total")}</dt><dd><bdi className="tabular-nums">{money(toFixed(totals.total))}</bdi></dd></div>
            </dl>
            <LookupSelect path="/customers" label={t("sales.customer")} value={customer} onChange={(id) => { setCustomer(id); touch(); }} allowEmpty={t("pos.walkIn")} error={needsCustomer ? t("errors.CUSTOMER_REQUIRED") : undefined} />
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1.5 text-sm font-medium">
                {t("fields.method")}
                <select value={method} onChange={(e) => { setMethod(e.target.value); touch(); }} className="h-10 w-full rounded-md border bg-card px-3 text-sm font-normal">
                  {PAYMENT_METHODS.map((m) => (
                    <option key={m} value={m}>{t(`method.${m}`)}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1.5 text-sm font-medium">
                {t("pos.tendered")}
                <input dir="ltr" inputMode="decimal" value={tendered} onChange={(e) => { setTendered(e.target.value); touch(); }} placeholder={toFixed(totals.total)} className="h-10 w-full rounded-md border bg-card px-3 text-sm font-normal tabular-nums" />
              </label>
            </div>
            {change > 0n ? <p className="flex justify-between text-sm"><span>{t("pos.change")}</span><bdi className="font-bold tabular-nums text-success">{money(toFixed(change))}</bdi></p> : null}
            {change < 0n && cart.length ? <p className="flex justify-between text-sm"><span>{t("pos.onCredit")}</span><bdi className="font-bold tabular-nums text-warning">{money(toFixed(-change))}</bdi></p> : null}
            {overpaidNonCash ? <p role="alert" className="text-xs text-danger">{t("errors.OVERPAYMENT")}</p> : null}
            {checkout.error ? (
              <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {errorMessage(checkout.error, t)}
                {stockDetail ? ` — ${shortName ?? ""} (${t("pos.available")}: ${stockDetail.available})` : ""}
              </p>
            ) : null}
            <Button className="h-12 w-full text-base" disabled={!canPay || checkout.isPending} onClick={pay}>
              {checkout.isPending ? t("pos.processing") : t("pos.pay")}
            </Button>
          </div>
        </Card>
      </div>

      <Modal open={receipt !== null} title={t("pos.done")} closeLabel={t("org.close")} onClose={() => { setReceipt(null); searchRef.current?.focus(); }}>
        {receipt ? <Receipt sale={receipt} footer={settings.data?.invoice_footer} /> : null}
      </Modal>
    </section>
  );
}
