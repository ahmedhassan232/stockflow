import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SearchInput } from "@/components/common/data";
import { SelectField } from "@/components/ui/input";
import { useAuth } from "@/features/auth/store";
import { useList } from "@/features/data/api";
import type { Named, Product, WarehouseItem } from "@/features/data/types";
import { formatMoney } from "@/utils/format";

export function useCurrency() {
  return useAuth((s) => s.me?.active_company?.currency ?? "EGP");
}

export function useMoney() {
  const { i18n } = useTranslation();
  const currency = useCurrency();
  return (value: string | number | null | undefined) => formatMoney(value, currency, i18n.language);
}

const WAREHOUSE_KEY = "stockflow.warehouse";

/** Remembers the last warehouse used on this device (a preference, not a permission:
 *  the server still checks that the user may access it). */
export function useWarehouseChoice() {
  const list = useList<WarehouseItem>("/warehouses", { page_size: 100, is_active: true });
  const [chosen, setChosen] = useState<string>(() => {
    try {
      return localStorage.getItem(WAREHOUSE_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const items = list.data?.items ?? [];
  const value = items.some((w) => w.id === chosen) ? chosen : (items[0]?.id ?? "");
  const set = (id: string) => {
    setChosen(id);
    try {
      localStorage.setItem(WAREHOUSE_KEY, id);
    } catch {
      /* ignore */
    }
  };
  return { warehouses: items, value, set, isPending: list.isPending };
}

export function LookupSelect({ path, label, value, onChange, allowEmpty, error }: { path: string; label: string; value: string; onChange: (id: string) => void; allowEmpty?: string; error?: string }) {
  const list = useList<Named>(path, { page_size: 100, is_active: true });
  return (
    <SelectField label={label} value={value} onChange={(e) => onChange(e.target.value)} error={error}>
      {allowEmpty !== undefined ? <option value="">{allowEmpty}</option> : <option value="" disabled />}
      {list.data?.items.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </SelectField>
  );
}

/** Type-ahead product search (name, SKU or barcode – searched on the server). */
export function ProductPicker({ onPick, exclude = [], trackedOnly }: { onPick: (product: Product) => void; exclude?: string[]; trackedOnly?: boolean }) {
  const { t } = useTranslation();
  const money = useMoney();
  const [q, setQ] = useState("");
  const results = useList<Product>("/products", { q, page_size: 8, is_active: true }, q.length > 0);
  const items = (results.data?.items ?? []).filter((p) => !exclude.includes(p.id) && (!trackedOnly || p.track_inventory));
  return (
    <div>
      <SearchInput placeholder={t("products.searchToAdd")} onSearch={setQ} className="max-w-none" />
      {q ? (
        <ul className="mt-1 max-h-56 divide-y overflow-y-auto rounded-md border bg-card text-sm">
          {results.isPending ? (
            <li className="px-3 py-2 text-muted-foreground">{t("common.loading")}</li>
          ) : items.length === 0 ? (
            <li className="px-3 py-2 text-muted-foreground">{t("products.noMatch")}</li>
          ) : (
            items.map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => onPick(p)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-start hover:bg-muted">
                  <span>
                    {p.name} <bdi className="font-mono text-xs text-muted-foreground">{p.sku}</bdi>
                  </span>
                  <bdi className="tabular-nums text-muted-foreground">{money(p.selling_price)}</bdi>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

export const decimalInput = "h-9 w-24 rounded-md border bg-card px-2 text-sm tabular-nums aria-[invalid=true]:border-danger";
