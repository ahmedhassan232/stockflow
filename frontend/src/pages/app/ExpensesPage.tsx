import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DataTable, ErrorAlert, FormActions, PageHeader, SearchInput, Stat, type Column } from "@/components/common/data";
import { ExportButton } from "@/components/common/ExportButton";
import { LookupSelect, decimalInput, useMoney } from "@/components/common/pickers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { useCan } from "@/features/auth/store";
import { newKey, useGet, useList, useSend, type Page } from "@/features/data/api";
import { PAYMENT_METHODS } from "@/features/data/types";
import { isPositive } from "@/utils/decimal";
import { formatDay } from "@/utils/format";

interface Expense {
  id: string;
  number: string;
  expense_date: string;
  category: string;
  description: string | null;
  amount: string;
  method: string;
  branch_name: string | null;
  status: "active" | "voided";
  void_reason: string | null;
  created_by_name: string | null;
}

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const DEFAULT_CATEGORIES = ["expenses.cat.rent", "expenses.cat.salaries", "expenses.cat.utilities", "expenses.cat.transport", "expenses.cat.maintenance", "expenses.cat.other"];

function ExpenseForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const send = useSend(["expenses", "reports"]);
  const used = useGet<string[]>("/expenses/categories");
  const [key] = useState(newKey);
  const [date, setDate] = useState(today());
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<string>("cash");
  const [description, setDescription] = useState("");
  const [branch, setBranch] = useState("");
  const suggestions = [...new Set([...(used.data ?? []), ...DEFAULT_CATEGORIES.map((k) => t(k))])];
  const amountOk = /^\d{1,12}(\.\d{1,2})?$/.test(amount) && isPositive(amount);
  const valid = amountOk && category.trim().length >= 2 && !!date && date <= today();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    send.mutate(
      { path: "/expenses", idempotencyKey: key, body: { expense_date: date, category: category.trim(), amount, method, description: description.trim() || null, branch_id: branch || null } },
      { onSuccess: onDone },
    );
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={t("fields.date")} type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
        <TextField label={t("fields.amount")} dir="ltr" inputMode="decimal" className={decimalInput} value={amount} onChange={(e) => setAmount(e.target.value)} error={amount && !amountOk ? t("validation.decimal") : undefined} />
        <div>
          <TextField label={t("expenses.category")} list="expense-categories" value={category} onChange={(e) => setCategory(e.target.value)} hint={t("expenses.categoryHint")} />
          <datalist id="expense-categories">
            {suggestions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>
        <SelectField label={t("fields.method")} value={method} onChange={(e) => setMethod(e.target.value)}>
          {PAYMENT_METHODS.map((m) => (
            <option key={m} value={m}>{t(`method.${m}`)}</option>
          ))}
        </SelectField>
      </div>
      <LookupSelect path="/branches" label={t("expenses.branch")} value={branch} onChange={setBranch} allowEmpty={t("expenses.wholeCompany")} />
      <TextField label={t("fields.description")} value={description} onChange={(e) => setDescription(e.target.value)} />
      <FormActions onCancel={onDone} pending={send.isPending} disabled={!valid} />
    </form>
  );
}

function VoidForm({ expense, onDone }: { expense: Expense; onDone: () => void }) {
  const { t } = useTranslation();
  const money = useMoney();
  const send = useSend(["expenses", "reports"]);
  const [reason, setReason] = useState("");
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim().length >= 3) send.mutate({ path: `/expenses/${expense.id}/void`, body: { reason: reason.trim() } }, { onSuccess: onDone });
      }}
    >
      <ErrorAlert error={send.error} />
      <p className="text-sm">
        {t("expenses.voidHint")} <bdi className="font-semibold">{expense.number} · {money(expense.amount)}</bdi>
      </p>
      <TextField label={t("inventory.reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
      <FormActions onCancel={onDone} pending={send.isPending} disabled={reason.trim().length < 3} submitLabel={t("expenses.void")} danger />
    </form>
  );
}

export function ExpensesPage() {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const canManage = useCan("expenses.manage");
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [modal, setModal] = useState<"new" | Expense | null>(null);
  const filters = { q, date_from: from, date_to: to };
  const list = useList<Expense>("/expenses", { ...filters, page, page_size: 15 });
  const totalAmount = (list.data as (Page<Expense> & { total_amount: string }) | undefined)?.total_amount;
  const dateInput = "h-10 rounded-md border bg-card px-3 text-sm";
  const columns: Column<Expense>[] = [
    { key: "number", header: t("fields.number"), render: (e) => <bdi className="font-mono text-xs">{e.number}</bdi> },
    { key: "date", header: t("fields.date"), render: (e) => <span className="whitespace-nowrap">{formatDay(e.expense_date, i18n.language)}</span> },
    {
      key: "category",
      header: t("expenses.category"),
      render: (e) => (
        <>
          <span className="font-medium">{e.category}</span>
          {e.description ? <span className="block text-xs text-muted-foreground">{e.description}</span> : null}
        </>
      ),
    },
    { key: "branch", header: t("expenses.branch"), render: (e) => e.branch_name ?? <span className="text-muted-foreground">{t("expenses.wholeCompany")}</span> },
    { key: "method", header: t("fields.method"), render: (e) => t(`method.${e.method}`) },
    { key: "amount", header: t("fields.amount"), align: "end", render: (e) => <bdi className={`font-semibold tabular-nums ${e.status === "voided" ? "text-muted-foreground line-through" : ""}`}>{money(e.amount)}</bdi> },
    {
      key: "status",
      header: t("org.status"),
      align: "end",
      className: "whitespace-nowrap py-2",
      render: (e) =>
        e.status === "voided" ? (
          <span title={e.void_reason ?? undefined}><Badge tone="danger">{t("expenses.voided")}</Badge></span>
        ) : canManage ? (
          <Button variant="ghost" size="sm" className="text-danger" onClick={() => setModal(e)}>{t("expenses.void")}</Button>
        ) : null,
    },
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("expenses.title")} subtitle={t("expenses.subtitle")}>
        <ExportButton path="/expenses/export" params={filters} filename="expenses.csv" />
        {canManage ? (
          <Button onClick={() => setModal("new")}>
            <Plus />
            {t("expenses.add")}
          </Button>
        ) : null}
      </PageHeader>
      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Stat label={t("expenses.totalFiltered")} value={<bdi>{money(totalAmount ?? "0")}</bdi>} hint={t("expenses.totalHint")} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b p-3">
          <SearchInput placeholder={t("expenses.search")} onSearch={(v) => { setQ(v); setPage(1); }} />
          <label className="flex items-center gap-2 text-sm">
            {t("reports.from")}
            <input type="date" value={from} max={to || undefined} onChange={(e) => { setFrom(e.target.value); setPage(1); }} className={dateInput} />
          </label>
          <label className="flex items-center gap-2 text-sm">
            {t("reports.to")}
            <input type="date" value={to} min={from || undefined} onChange={(e) => { setTo(e.target.value); setPage(1); }} className={dateInput} />
          </label>
        </div>
        <DataTable query={list} columns={columns} rowKey={(e) => e.id} empty={t("expenses.empty")} page={page} pageSize={15} onPage={setPage} minWidth="48rem" />
      </Card>
      <Modal open={modal !== null} title={t(modal === "new" ? "expenses.add" : "expenses.void")} closeLabel={t("org.close")} onClose={() => setModal(null)}>
        {modal === "new" ? <ExpenseForm onDone={() => setModal(null)} /> : modal ? <VoidForm expense={modal} onDone={() => setModal(null)} /> : null}
      </Modal>
    </section>
  );
}
