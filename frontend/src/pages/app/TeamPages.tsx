import { Plus, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { DataTable, ErrorAlert, FormActions, PageHeader, type Column } from "@/components/common/data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { useCan } from "@/features/auth/store";
import { useGet, useList, useSend } from "@/features/data/api";
import type { Named } from "@/features/data/types";

interface Employee {
  id: string;
  full_name: string;
  email: string;
  role_id: string;
  role_code: string;
  role_name: string;
  status: "active" | "suspended" | "invited";
  has_password: boolean;
  restricted_to_branches: boolean;
  branch_ids: string[];
  is_self: boolean;
}
interface Role {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_owner: boolean;
  permissions: string[];
  member_count: number;
}
interface Permission {
  code: string;
  description: string;
  group: string;
}

const asList = <T,>(q: { data?: T[]; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }) => ({ ...q, data: q.data ? { items: q.data } : undefined });

/** Built-in role names come from the server in English; show them translated. */
function useRoleName() {
  const { t } = useTranslation();
  return (role: { code: string; name: string; is_system?: boolean }) => {
    const key = `roles.names.${role.code}`;
    const translated = t(key);
    return translated === key ? role.name : translated;
  };
}

function BranchScope({ all, setAll, selected, setSelected }: { all: boolean; setAll: (v: boolean) => void; selected: string[]; setSelected: (ids: string[]) => void }) {
  const { t } = useTranslation();
  const branches = useList<Named>("/branches", { page_size: 100 });
  return (
    <fieldset className="space-y-2 rounded-md border p-3 text-sm">
      <legend className="px-1 font-medium">{t("team.branchAccess")}</legend>
      <label className="flex items-center gap-2">
        <input type="checkbox" className="size-4" checked={all} onChange={(e) => setAll(e.target.checked)} />
        {t("org.allBranches")}
      </label>
      {!all ? (
        <div className="grid gap-1 ps-6 sm:grid-cols-2">
          {branches.data?.items.map((b) => (
            <label key={b.id} className="flex items-center gap-2">
              <input type="checkbox" className="size-4" checked={selected.includes(b.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, b.id] : selected.filter((id) => id !== b.id))} />
              {b.name}
            </label>
          ))}
          {selected.length === 0 ? <p className="text-xs text-warning sm:col-span-2">{t("team.noBranchWarning")}</p> : null}
        </div>
      ) : null}
    </fieldset>
  );
}

function EmployeeForm({ employee, roles, onDone }: { employee: Employee | null; roles: Role[]; onDone: () => void }) {
  const { t } = useTranslation();
  const roleName = useRoleName();
  const send = useSend(["employees", "roles"]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(employee?.role_id ?? "");
  const [all, setAll] = useState(!(employee?.restricted_to_branches ?? false));
  const [branches, setBranches] = useState<string[]>(employee?.branch_ids ?? []);
  const valid = !!role && (employee !== null || (name.trim().length >= 2 && /^\S+@\S+\.\S+$/.test(email)));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    const scope = all ? null : branches;
    send.mutate(
      employee
        ? { method: "patch", path: `/employees/${employee.id}`, body: { role_id: role, ...(all ? { restricted_to_branches: false } : { branch_ids: branches }) } }
        : { path: "/employees", body: { full_name: name.trim(), email: email.trim(), role_id: role, branch_ids: scope } },
      { onSuccess: onDone },
    );
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      {employee ? (
        <p className="text-sm text-muted-foreground">{employee.full_name} · <bdi>{employee.email}</bdi></p>
      ) : (
        <>
          <TextField label={t("auth.fullName")} value={name} onChange={(e) => setName(e.target.value)} />
          <TextField label={t("auth.email")} type="email" dir="ltr" value={email} onChange={(e) => setEmail(e.target.value)} hint={t("team.inviteHint")} />
        </>
      )}
      <SelectField label={t("org.role")} value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="" disabled />
        {roles.map((r) => (
          <option key={r.id} value={r.id}>{roleName(r)}</option>
        ))}
      </SelectField>
      <BranchScope all={all} setAll={setAll} selected={branches} setSelected={setBranches} />
      <FormActions onCancel={onDone} pending={send.isPending} disabled={!valid} submitLabel={employee ? undefined : t("team.sendInvite")} />
    </form>
  );
}

export function EmployeesPage() {
  const { t } = useTranslation();
  const roleName = useRoleName();
  const canManage = useCan("employees.manage");
  const list = useGet<Employee[]>("/employees");
  const roles = useGet<Role[]>("/roles");
  const send = useSend(["employees", "roles"]);
  const [editing, setEditing] = useState<Employee | "new" | null>(null);
  const [removing, setRemoving] = useState<Employee | null>(null);
  const columns: Column<Employee>[] = [
    {
      key: "name",
      header: t("fields.name"),
      render: (e) => (
        <>
          <span className="font-medium">{e.full_name}</span> {e.is_self ? <span className="text-xs text-muted-foreground">({t("team.you")})</span> : null}
          <bdi className="block text-xs text-muted-foreground">{e.email}</bdi>
        </>
      ),
    },
    { key: "role", header: t("org.role"), render: (e) => roleName({ code: e.role_code, name: e.role_name }) },
    { key: "branches", header: t("org.branchScope"), render: (e) => (e.restricted_to_branches ? t("org.someBranches", { count: e.branch_ids.length }) : t("org.allBranches")) },
    {
      key: "status",
      header: t("org.status"),
      render: (e) => (!e.has_password ? <Badge tone="warning">{t("team.pending")}</Badge> : <Badge tone={e.status === "active" ? "success" : "danger"}>{t(e.status === "active" ? "org.active" : "team.suspended")}</Badge>),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("org.actions"),
            align: "end" as const,
            className: "whitespace-nowrap py-2",
            render: (e: Employee) =>
              e.is_self ? null : (
                <>
                  <Button variant="ghost" size="sm" onClick={() => setEditing(e)}>{t("org.edit")}</Button>
                  <Button variant="ghost" size="sm" disabled={send.isPending} onClick={() => send.mutate({ method: "patch", path: `/employees/${e.id}`, body: { status: e.status === "active" ? "suspended" : "active" } })}>
                    {t(e.status === "active" ? "team.suspend" : "org.activate")}
                  </Button>
                  <Button variant="ghost" size="icon" className="size-9 text-danger" aria-label={t("team.remove")} onClick={() => { send.reset(); setRemoving(e); }}>
                    <Trash2 />
                  </Button>
                </>
              ),
          },
        ]
      : []),
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("team.title")} subtitle={t("team.subtitle")}>
        {canManage ? (
          <Button onClick={() => setEditing("new")}>
            <UserPlus />
            {t("team.invite")}
          </Button>
        ) : null}
      </PageHeader>
      {send.error && !removing ? <div className="mb-3"><ErrorAlert error={send.error} /></div> : null}
      <Card>
        <DataTable query={asList(list)} columns={columns} rowKey={(e) => e.id} empty={t("team.empty")} minWidth="44rem" />
      </Card>
      <Modal open={editing !== null} title={t(editing === "new" ? "team.invite" : "team.editAccess")} closeLabel={t("org.close")} onClose={() => setEditing(null)}>
        {editing !== null ? <EmployeeForm key={editing === "new" ? "new" : editing.id} employee={editing === "new" ? null : editing} roles={roles.data ?? []} onDone={() => setEditing(null)} /> : null}
      </Modal>
      <Modal open={removing !== null} title={t("team.remove")} closeLabel={t("org.close")} onClose={() => setRemoving(null)}>
        <p className="text-sm">{t("team.confirmRemove", { name: removing?.full_name ?? "" })}</p>
        <div className="mt-3"><ErrorAlert error={send.error} /></div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setRemoving(null)}>{t("org.cancel")}</Button>
          <Button className="bg-danger text-white hover:bg-danger/90" disabled={send.isPending} onClick={() => removing && send.mutate({ method: "delete", path: `/employees/${removing.id}` }, { onSuccess: () => setRemoving(null) })}>
            {t("team.remove")}
          </Button>
        </div>
      </Modal>
    </section>
  );
}

function RoleForm({ role, catalogue, onDone }: { role: Role | null; catalogue: Permission[]; onDone: () => void }) {
  const { t } = useTranslation();
  const roleName = useRoleName();
  const send = useSend(["roles", "employees"]);
  const [name, setName] = useState(role ? roleName(role) : "");
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const groups = [...new Set(catalogue.map((p) => p.group))];
  const toggle = (codes: string[], on: boolean) =>
    setChosen((prev) => {
      const next = new Set(prev);
      for (const c of codes) if (on) next.add(c); else next.delete(c);
      return next;
    });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim().length < 2) return;
    send.mutate({ method: role ? "put" : "post", path: role ? `/roles/${role.id}` : "/roles", body: { name: role?.is_system ? role.name : name.trim(), description: role?.description ?? null, permissions: [...chosen] } }, { onSuccess: onDone });
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <ErrorAlert error={send.error} />
      <TextField label={t("roles.name")} value={name} disabled={role?.is_system} onChange={(e) => setName(e.target.value)} />
      <div className="grid gap-3 sm:grid-cols-2">
        {groups.map((group) => {
          const items = catalogue.filter((p) => p.group === group);
          const allOn = items.every((p) => chosen.has(p.code));
          return (
            <fieldset key={group} className="rounded-md border p-3 text-sm">
              <legend className="px-1">
                <label className="flex items-center gap-2 font-semibold">
                  <input type="checkbox" className="size-4" checked={allOn} onChange={(e) => toggle(items.map((p) => p.code), e.target.checked)} />
                  {t(`permGroups.${group}`)}
                </label>
              </legend>
              <div className="space-y-1.5">
                {items.map((p) => (
                  <label key={p.code} className="flex items-start gap-2">
                    <input type="checkbox" className="mt-0.5 size-4" checked={chosen.has(p.code)} onChange={(e) => toggle([p.code], e.target.checked)} />
                    <span>{t(`perms.${p.code.replaceAll(".", "_")}`, { defaultValue: p.description })}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          );
        })}
      </div>
      <FormActions onCancel={onDone} pending={send.isPending} disabled={name.trim().length < 2} />
    </form>
  );
}

export function RolesPage() {
  const { t } = useTranslation();
  const roleName = useRoleName();
  const canManage = useCan("roles.manage");
  const roles = useGet<Role[]>("/roles");
  const catalogue = useGet<Permission[]>("/roles/permissions");
  const send = useSend(["roles"]);
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const total = catalogue.data?.length ?? 0;
  const columns: Column<Role>[] = [
    {
      key: "name",
      header: t("roles.name"),
      render: (r) => (
        <span className="flex items-center gap-2 font-medium">
          <ShieldCheck className="size-4 text-secondary" aria-hidden="true" />
          {roleName(r)}
        </span>
      ),
    },
    { key: "type", header: t("roles.type"), render: (r) => <Badge tone={r.is_system ? "neutral" : "success"}>{t(r.is_system ? "roles.builtIn" : "roles.custom")}</Badge> },
    { key: "perms", header: t("org.permissions"), render: (r) => <bdi className="tabular-nums">{r.is_owner ? t("roles.all") : `${r.permissions.length} / ${total}`}</bdi> },
    { key: "members", header: t("roles.members"), render: (r) => r.member_count },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("org.actions"),
            align: "end" as const,
            className: "whitespace-nowrap py-2",
            render: (r: Role) =>
              r.is_owner ? (
                <span className="text-xs text-muted-foreground">{t("roles.ownerLocked")}</span>
              ) : (
                <>
                  <Button variant="ghost" size="sm" onClick={() => setEditing(r)}>{t("roles.editPermissions")}</Button>
                  {!r.is_system ? (
                    <Button variant="ghost" size="icon" className="size-9 text-danger" aria-label={t("common.delete")} disabled={send.isPending} onClick={() => send.mutate({ method: "delete", path: `/roles/${r.id}` })}>
                      <Trash2 />
                    </Button>
                  ) : null}
                </>
              ),
          },
        ]
      : []),
  ];
  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader title={t("roles.title")} subtitle={t("roles.subtitle")}>
        {canManage ? (
          <Button onClick={() => setEditing("new")}>
            <Plus />
            {t("roles.add")}
          </Button>
        ) : null}
      </PageHeader>
      {send.error ? <div className="mb-3"><ErrorAlert error={send.error} /></div> : null}
      <Card>
        <DataTable query={asList(roles)} columns={columns} rowKey={(r) => r.id} empty={t("team.empty")} minWidth="40rem" />
      </Card>
      <Modal open={editing !== null} title={t(editing === "new" ? "roles.add" : "roles.editPermissions")} closeLabel={t("org.close")} onClose={() => setEditing(null)} wide>
        {editing !== null ? <RoleForm key={editing === "new" ? "new" : editing.id} role={editing === "new" ? null : editing} catalogue={catalogue.data ?? []} onDone={() => setEditing(null)} /> : null}
      </Modal>
    </section>
  );
}
