import { Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/utils/cn";
import { errorMessage } from "@/utils/errors";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

export function ErrorAlert({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
      {errorMessage(error, t)}
    </p>
  );
}

/** Debounced search box: `onSearch` fires 300 ms after typing stops. */
export function SearchInput({ onSearch, placeholder, className, autoFocus }: { onSearch: (q: string) => void; placeholder: string; className?: string; autoFocus?: boolean }) {
  const [value, setValue] = useState("");
  useEffect(() => {
    const id = setTimeout(() => onSearch(value.trim()), 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <label className={cn("relative block w-full max-w-sm", className)}>
      <span className="sr-only">{placeholder}</span>
      <Search className="pointer-events-none absolute start-3 top-3 size-4 text-muted-foreground" aria-hidden="true" />
      <input
        type="search"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="h-10 w-full rounded-md border bg-card pe-3 ps-9 text-sm placeholder:text-muted-foreground"
      />
    </label>
  );
}

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "start" | "end";
  className?: string;
}

interface QueryLike<T> {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data?: { items: T[]; total?: number } | undefined;
  refetch: () => unknown;
}

interface TableProps<T> {
  query: QueryLike<T>;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  empty: string;
  onRowClick?: (row: T) => void;
  page?: number;
  pageSize?: number;
  onPage?: (page: number) => void;
  minWidth?: string;
}

/** Table with the four states every data view needs: loading, error (+retry), empty, data. */
export function DataTable<T>({ query, columns, rowKey, empty, onRowClick, page, pageSize, onPage, minWidth = "40rem" }: TableProps<T>) {
  const { t } = useTranslation();
  if (query.isPending) {
    return (
      <div className="space-y-2 p-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div role="alert" className="flex flex-col items-center gap-3 p-10 text-center">
        <p className="text-sm text-danger">{errorMessage(query.error, t)}</p>
        <Button variant="outline" onClick={() => void query.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }
  const { items, total = items.length } = query.data;
  if (items.length === 0) return <p className="p-10 text-center text-sm text-muted-foreground">{empty}</p>;
  const pages = pageSize ? Math.max(1, Math.ceil(total / pageSize)) : 1;
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth }}>
          <thead className="bg-muted/60 text-xs text-muted-foreground">
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={cn("px-4 py-3 font-medium", c.align === "end" ? "text-end" : "text-start")}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((row) => (
              <tr
                key={rowKey(row)}
                className={onRowClick ? "cursor-pointer hover:bg-muted/40" : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row) : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-4 py-3", c.align === "end" && "text-end", c.className)}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {page && onPage && pageSize ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 text-sm text-muted-foreground">
          <span>{t("org.total", { total })}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
              {t("org.prev")}
            </Button>
            <span>{t("org.pageOf", { page, pages })}</span>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
              {t("org.next")}
            </Button>
          </div>
        </div>
      ) : null}
    </>
  );
}

export function Tabs<K extends string>({ tabs, value, onChange }: { tabs: { key: K; label: string }[]; value: K; onChange: (key: K) => void }) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          type="button"
          aria-selected={value === tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium",
            value === tab.key ? "border-secondary text-secondary" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "danger" | "success" }) {
  return (
    <div className="rounded-lg border bg-card p-5 shadow-card">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-2xl font-bold tabular-nums", tone === "danger" && "text-danger", tone === "success" && "text-success")}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function FormActions({ onCancel, pending, submitLabel, danger, disabled }: { onCancel: () => void; pending: boolean; submitLabel?: string; danger?: boolean; disabled?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex justify-end gap-2 pt-2">
      <Button variant="outline" onClick={onCancel}>
        {t("org.cancel")}
      </Button>
      <Button type="submit" disabled={pending || disabled} className={danger ? "bg-danger text-white hover:bg-danger/90" : undefined}>
        {pending ? t("org.saving") : (submitLabel ?? t("org.save"))}
      </Button>
    </div>
  );
}
