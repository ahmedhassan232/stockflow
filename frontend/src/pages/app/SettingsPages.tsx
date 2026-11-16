import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DataTable, ErrorAlert, PageHeader, type Column } from "@/components/common/data";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchMe } from "@/features/auth/api";
import { useCan } from "@/features/auth/store";
import { useGet, useList, useSend } from "@/features/data/api";
import { formatDateTime } from "@/utils/format";

interface CompanySettings {
  name: string;
  slug: string;
  legal_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  currency: string;
  timezone: string;
  tax_number: string | null;
  default_tax_rate: string;
  allow_negative_stock: boolean;
  invoice_footer: string | null;
}
const CURRENCIES = ["EGP", "SAR", "AED", "KWD", "QAR", "BHD", "OMR", "JOD", "USD", "EUR", "GBP"];
const ZONES = ["Africa/Cairo", "Asia/Riyadh", "Asia/Dubai", "Asia/Kuwait", "Asia/Qatar", "Asia/Amman", "Africa/Casablanca", "Europe/London", "UTC"];
const TEXT = ["name", "legal_name", "email", "phone", "address", "tax_number", "invoice_footer"] as const;

export function SettingsPage() {
  const { t } = useTranslation();
  const canEdit = useCan("settings.update");
  const query = useGet<CompanySettings>("/settings");
  const send = useSend<CompanySettings>(["settings"]);
  const [form, setForm] = useState<CompanySettings | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);
  if (query.isPending) return <Skeleton className="mx-auto h-96 max-w-3xl" />;
  if (!form) return <ErrorAlert error={query.error} />;
  const set = <K extends keyof CompanySettings>(key: K, value: CompanySettings[K]) => {
    setSaved(false);
    setForm({ ...form, [key]: value });
  };
  const rateOk = /^\d{1,3}(\.\d{1,2})?$/.test(form.default_tax_rate) && Number(form.default_tax_rate) <= 100;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!rateOk || form.name.trim().length < 2) return;
    const body: Record<string, unknown> = { currency: form.currency, timezone: form.timezone, default_tax_rate: form.default_tax_rate, allow_negative_stock: form.allow_negative_stock };
    for (const key of TEXT) body[key] = (form[key] ?? "").trim() || (key === "name" ? form.name : null);
    send.mutate(
      { method: "patch", path: "/settings", body },
      {
        onSuccess: () => {
          setSaved(true);
          void fetchMe(); // company name / currency shown across the app
        },
      },
    );
  };
  const text = (key: (typeof TEXT)[number], label: string, extra?: { dir?: "ltr"; type?: string }) => (
    <TextField label={t(label)} disabled={!canEdit} value={form[key] ?? ""} onChange={(e) => set(key, e.target.value)} {...extra} />
  );
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <ErrorAlert error={send.error} />
        {saved ? <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">{t("settings.saved")}</p> : null}
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">{t("settings.company")}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {text("name", "auth.companyName")}
            {text("legal_name", "settings.legalName")}
            {text("email", "fields.email", { dir: "ltr", type: "email" })}
            {text("phone", "fields.phone", { dir: "ltr" })}
            {text("tax_number", "fields.taxNumber", { dir: "ltr" })}
            {text("address", "fields.address")}
          </div>
        </Card>
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">{t("settings.regional")}</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <SelectField label={t("org.currency")} disabled={!canEdit} value={form.currency} onChange={(e) => set("currency", e.target.value)}>
              {[...new Set([form.currency, ...CURRENCIES])].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </SelectField>
            <SelectField label={t("settings.timezone")} disabled={!canEdit} value={form.timezone} onChange={(e) => set("timezone", e.target.value)}>
              {[...new Set([form.timezone, ...ZONES])].map((z) => (
                <option key={z} value={z}>{z}</option>
              ))}
            </SelectField>
            <TextField label={t("settings.defaultTax")} dir="ltr" inputMode="decimal" disabled={!canEdit} value={form.default_tax_rate} onChange={(e) => set("default_tax_rate", e.target.value)} error={rateOk ? undefined : t("validation.decimal")} />
          </div>
          <p className="text-xs text-muted-foreground">{t("settings.currencyHint")}</p>
        </Card>
        <Card className="space-y-4 p-5">
          <h2 className="font-semibold">{t("settings.sales")}</h2>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-4" disabled={!canEdit} checked={form.allow_negative_stock} onChange={(e) => set("allow_negative_stock", e.target.checked)} />
            <span>
              <span className="font-medium">{t("settings.allowNegative")}</span>
              <span className="block text-xs text-muted-foreground">{t("settings.allowNegativeHint")}</span>
            </span>
          </label>
          {text("invoice_footer", "settings.invoiceFooter")}
        </Card>
        {canEdit ? (
          <div className="flex justify-end">
            <Button type="submit" disabled={send.isPending}>{send.isPending ? t("org.saving") : t("org.save")}</Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t("settings.readOnly")}</p>
        )}
      </form>
    </section>
  );
}

interface AuditRow {
  id: string;
  action: string;
  entity_type: string;
  summary: string | null;
  data: Record<string, unknown> | null;
  user_name: string | null;
  created_at: string;
}

export function AuditLogPage() {
  const { t, i18n } = useTranslation();
  const [page, setPage] = useState(1);
  const list = useList<AuditRow>("/audit-logs", { page, page_size: 20 });
  const columns: Column<AuditRow>[] = [
    { key: "date", header: t("fields.date"), render: (r) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.created_at, i18n.language)}</span> },
    { key: "user", header: t("audit.user"), render: (r) => r.user_name ?? "—" },
    { key: "action", header: t("audit.action"), render: (r) => t(`audit.actions.${r.action.replace(".", "_")}`, { defaultValue: r.action }) },
    { key: "summary", header: t("audit.details"), render: (r) => <bdi className="text-muted-foreground">{[r.summary, typeof r.data?.reason === "string" ? r.data.reason : null].filter(Boolean).join(" — ") || "—"}</bdi> },
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")} />
      <Card>
        <DataTable query={list} columns={columns} rowKey={(r) => r.id} empty={t("audit.empty")} page={page} pageSize={20} onPage={setPage} />
      </Card>
    </section>
  );
}
