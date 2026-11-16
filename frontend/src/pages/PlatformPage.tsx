import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate } from "react-router-dom";
import { DataTable, ErrorAlert, PageHeader, type Column } from "@/components/common/data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { useAuth } from "@/features/auth/store";
import { useGet, useSend } from "@/features/data/api";
import { formatDateTime } from "@/utils/format";

interface TenantRow {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended";
  currency: string;
  created_at: string;
  member_count: number;
  owner_name: string | null;
  owner_email: string | null;
}

interface AuditRow {
  id: string;
  action: string;
  company_name: string;
  actor_name: string;
  actor_email: string;
  created_at: string;
}

/** Operator console. The API refuses non-admins; this guard only avoids showing a dead page. */
export function PlatformPage() {
  const { t, i18n } = useTranslation();
  const me = useAuth((s) => s.me);
  const isAdmin = !!me?.user.is_platform_admin;
  const query = useGet<TenantRow[]>("/platform/tenants", undefined, isAdmin);
  const audit = useGet<AuditRow[]>("/platform/audit-log", undefined, isAdmin);
  const send = useSend(["platform"]);
  const [target, setTarget] = useState<TenantRow | null>(null);
  if (!isAdmin) return <Navigate to="/app" replace />;
  const rows = query.data ?? [];
  const columns: Column<TenantRow>[] = [
    {
      key: "name",
      header: t("platform.company"),
      render: (r) => (
        <>
          <span className="font-medium">{r.name}</span>
          <bdi className="block font-mono text-xs text-muted-foreground">{r.slug}</bdi>
        </>
      ),
    },
    {
      key: "owner",
      header: t("platform.owner"),
      render: (r) => (
        <>
          {r.owner_name ?? "—"}
          <bdi className="block text-xs text-muted-foreground">{r.owner_email}</bdi>
        </>
      ),
    },
    { key: "members", header: t("roles.members"), render: (r) => r.member_count },
    { key: "created", header: t("platform.created"), render: (r) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.created_at, i18n.language)}</span> },
    { key: "status", header: t("org.status"), render: (r) => <Badge tone={r.status === "active" ? "success" : "danger"}>{t(r.status === "active" ? "org.active" : "team.suspended")}</Badge> },
    {
      key: "actions",
      header: t("org.actions"),
      align: "end",
      className: "py-2",
      render: (r) =>
        r.id === me?.active_company?.tenant_id ? null : (
          <Button variant="ghost" size="sm" className={r.status === "active" ? "text-danger" : ""} onClick={() => { send.reset(); setTarget(r); }}>
            {t(r.status === "active" ? "team.suspend" : "org.activate")}
          </Button>
        ),
    },
  ];
  const auditColumns: Column<AuditRow>[] = [
    { key: "at", header: t("platform.when"), render: (r) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(r.created_at, i18n.language)}</span> },
    { key: "action", header: t("platform.action"), render: (r) => <Badge tone={r.action.endsWith("suspended") ? "danger" : "success"}>{t(r.action.endsWith("suspended") ? "platform.actSuspended" : "platform.actActivated")}</Badge> },
    { key: "company", header: t("platform.company"), render: (r) => r.company_name },
    {
      key: "actor",
      header: t("platform.actor"),
      render: (r) => (
        <>
          {r.actor_name}
          <bdi className="block text-xs text-muted-foreground">{r.actor_email}</bdi>
        </>
      ),
    },
  ];
  const suspending = target?.status === "active";
  return (
    <main className="mx-auto max-w-6xl p-4 sm:p-8">
      <PageHeader title={t("platform.title")} subtitle={t("platform.subtitle")}>
        <Link to="/app" className="text-sm text-secondary hover:underline">{t("platform.backToApp")}</Link>
      </PageHeader>
      <p className="mb-4 text-sm text-muted-foreground">
        {t("platform.summary", { total: rows.length, suspended: rows.filter((r) => r.status === "suspended").length })}
      </p>
      <Card>
        <DataTable query={{ ...query, data: query.data ? { items: rows } : undefined }} columns={columns} rowKey={(r) => r.id} empty={t("team.empty")} minWidth="52rem" />
      </Card>
      <h2 className="mb-1 mt-8 text-lg font-semibold">{t("platform.auditTitle")}</h2>
      <p className="mb-3 text-sm text-muted-foreground">{t("platform.auditHint")}</p>
      <Card>
        <DataTable query={{ ...audit, data: audit.data ? { items: audit.data } : undefined }} columns={auditColumns} rowKey={(r) => r.id} empty={t("platform.auditEmpty")} minWidth="40rem" />
      </Card>
      <Modal open={target !== null} title={t(suspending ? "platform.suspendTitle" : "platform.activateTitle")} closeLabel={t("org.close")} onClose={() => setTarget(null)}>
        <p className="text-sm">{t(suspending ? "platform.suspendHint" : "platform.activateHint", { name: target?.name ?? "" })}</p>
        <div className="mt-3"><ErrorAlert error={send.error} /></div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setTarget(null)}>{t("org.cancel")}</Button>
          <Button
            className={suspending ? "bg-danger text-white hover:bg-danger/90" : ""}
            disabled={send.isPending}
            onClick={() => target && send.mutate({ method: "patch", path: `/platform/tenants/${target.id}`, body: { status: suspending ? "suspended" : "active" } }, { onSuccess: () => setTarget(null) })}
          >
            {t(suspending ? "team.suspend" : "org.activate")}
          </Button>
        </div>
      </Modal>
    </main>
  );
}
