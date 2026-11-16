import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Power, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { Column, DataTable, ErrorAlert, FormActions, PageHeader, SearchInput } from "@/components/common/data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { useCan } from "@/features/auth/store";
import { useList, useSend } from "@/features/data/api";

export interface Field {
  name: string;
  label: string;
  type?: "text" | "email" | "tel" | "decimal" | "select" | "checkbox";
  required?: boolean;
  /** decimal: allowed fraction digits (money = 2, cost = 4) */
  places?: number;
  max?: number;
  ltr?: boolean;
  createOnly?: boolean;
  /** select: load options from this list endpoint (items need id + name) */
  optionsPath?: string;
  hint?: string;
  defaultValue?: string | boolean;
}

export interface CrudConfig<T> {
  path: string;
  title: string;
  subtitle: string;
  addLabel: string;
  empty: string;
  managePermission: string | { create: string; update: string; remove?: string };
  fields: Field[];
  columns: Column<T>[];
  /** other cached resources that depend on this one */
  alsoInvalidate?: string[];
  canDelete?: boolean;
  extraActions?: (row: T) => ReactNode;
}

type Row = { id: string; name: string; is_active: boolean } & Record<string, unknown>;
type Values = Record<string, string | boolean>;

function buildSchema(fields: Field[]) {
  const shape: Record<string, z.ZodType> = {};
  for (const f of fields) {
    if (f.type === "checkbox") shape[f.name] = z.boolean();
    else if (f.type === "decimal") {
      const pattern = new RegExp(`^\\d{1,10}(\\.\\d{1,${f.places ?? 2}})?$`);
      shape[f.name] = z
        .string()
        .trim()
        .refine((v) => (v === "" ? !f.required : pattern.test(v)), "validation.decimal")
        .refine((v) => v === "" || f.max === undefined || Number(v) <= f.max, "validation.tooLarge");
    } else if (f.type === "email") shape[f.name] = z.string().trim().refine((v) => v === "" || /^\S+@\S+\.\S+$/.test(v), "validation.email");
    else shape[f.name] = f.required ? z.string().trim().min(1, "validation.required") : z.string().trim();
  }
  return z.object(shape);
}

function SelectOptions({ field, register, error }: { field: Field; register: ReturnType<typeof useForm<Values>>["register"]; error?: string }) {
  const { t } = useTranslation();
  const options = useList<{ id: string; name: string }>(field.optionsPath ?? "", { page_size: 100, is_active: true }, !!field.optionsPath);
  return (
    <SelectField label={t(field.label)} error={error} {...register(field.name)}>
      <option value="">{t("common.none")}</option>
      {options.data?.items.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </SelectField>
  );
}

function ItemForm<T extends Row>({ config, item, onDone }: { config: CrudConfig<T>; item: T | null; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useSend<T>([config.path.slice(1), ...(config.alsoInvalidate ?? [])]);
  const fields = config.fields;
  const defaults: Values = {};
  for (const f of fields) {
    const current = item?.[f.name];
    defaults[f.name] = f.type === "checkbox" ? ((current as boolean | undefined) ?? f.defaultValue ?? false) : current == null ? ((f.defaultValue as string) ?? "") : String(current);
  }
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(buildSchema(fields)) as never, defaultValues: defaults });
  const error = (name: string) => {
    const m = formState.errors[name]?.message;
    return typeof m === "string" ? t(m) : undefined;
  };

  const onSubmit = handleSubmit(async (values) => {
    const body: Record<string, unknown> = {};
    for (const f of fields) {
      if (item && f.createOnly) continue;
      const v = values[f.name];
      if (f.type === "checkbox") body[f.name] = v;
      else if (v === "") {
        // decimals have a server default on create; other optional fields are cleared
        if (f.type !== "decimal") body[f.name] = null;
        else if (item) continue;
      } else body[f.name] = v; // decimals stay strings: no float ever touches money
    }
    if (!item) for (const key of Object.keys(body)) if (body[key] === null) delete body[key];
    await save.mutateAsync({ method: item ? "patch" : "post", path: item ? `${config.path}/${item.id}` : config.path, body }).then(onDone, () => undefined);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <ErrorAlert error={save.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) =>
          f.type === "checkbox" ? (
            <label key={f.name} className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" className="size-4" {...register(f.name)} />
              {t(f.label)}
            </label>
          ) : f.type === "select" ? (
            <SelectOptions key={f.name} field={f} register={register} error={error(f.name)} />
          ) : (
            <TextField
              key={f.name}
              label={t(f.label)}
              type={f.type === "email" ? "email" : f.type === "tel" ? "tel" : "text"}
              inputMode={f.type === "decimal" ? "decimal" : undefined}
              dir={f.ltr || f.type === "decimal" || f.type === "email" || f.type === "tel" ? "ltr" : undefined}
              disabled={!!item && f.createOnly}
              hint={f.hint ? t(f.hint) : undefined}
              error={error(f.name)}
              {...register(f.name)}
            />
          ),
        )}
      </div>
      <FormActions onCancel={onDone} pending={save.isPending} />
    </form>
  );
}

const PAGE_SIZE = 15;

export function CrudPage<T extends Row>({ config }: { config: CrudConfig<T> }) {
  const { t } = useTranslation();
  const perms = typeof config.managePermission === "string" ? { create: config.managePermission, update: config.managePermission, remove: config.managePermission } : config.managePermission;
  const canCreate = useCan(perms.create);
  const canUpdate = useCan(perms.update);
  const canRemove = useCan(perms.remove ?? "__none__") && !!config.canDelete;
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<T | "new" | null>(null);
  const [removing, setRemoving] = useState<T | null>(null);
  const list = useList<T>(config.path, { page, page_size: PAGE_SIZE, q });
  const send = useSend([config.path.slice(1), ...(config.alsoInvalidate ?? [])]);

  const columns: Column<T>[] = [
    ...config.columns,
    {
      key: "_status",
      header: t("org.status"),
      render: (row) => <Badge tone={row.is_active ? "success" : "neutral"}>{t(row.is_active ? "org.active" : "org.inactiveStatus")}</Badge>,
    },
    ...(canUpdate || canRemove
      ? [
          {
            key: "_actions",
            header: t("org.actions"),
            align: "end" as const,
            className: "whitespace-nowrap py-2",
            render: (row: T) => (
              <>
                {config.extraActions?.(row)}
                {canUpdate ? (
                  <>
                    <Button variant="ghost" size="sm" onClick={() => setEditing(row)}>
                      <Pencil />
                      {t("org.edit")}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={send.isPending} onClick={() => send.mutate({ method: "patch", path: `${config.path}/${row.id}`, body: { is_active: !row.is_active } })}>
                      <Power />
                      {t(row.is_active ? "org.deactivate" : "org.activate")}
                    </Button>
                  </>
                ) : null}
                {canRemove ? (
                  <Button variant="ghost" size="sm" className="text-danger" onClick={() => { send.reset(); setRemoving(row); }}>
                    <Trash2 />
                    {t("common.delete")}
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
      <PageHeader title={t(config.title)} subtitle={t(config.subtitle)}>
        {canCreate ? (
          <Button onClick={() => setEditing("new")}>
            <Plus />
            {t(config.addLabel)}
          </Button>
        ) : null}
      </PageHeader>
      <Card>
        <div className="border-b p-3">
          <SearchInput placeholder={t("org.search")} onSearch={(v) => { setQ(v); setPage(1); }} />
        </div>
        <DataTable query={list} columns={columns} rowKey={(r) => r.id} empty={t(config.empty)} page={page} pageSize={PAGE_SIZE} onPage={setPage} />
      </Card>

      <Modal open={editing !== null} title={t(editing === "new" ? config.addLabel : "org.edit")} closeLabel={t("org.close")} onClose={() => setEditing(null)} wide={config.fields.length > 5}>
        {editing !== null ? <ItemForm key={editing === "new" ? "new" : editing.id} config={config} item={editing === "new" ? null : editing} onDone={() => setEditing(null)} /> : null}
      </Modal>

      <Modal open={removing !== null} title={t("common.delete")} closeLabel={t("org.close")} onClose={() => setRemoving(null)}>
        <p className="text-sm">{t("common.confirmDelete", { name: removing?.name ?? "" })}</p>
        <div className="mt-3">
          <ErrorAlert error={send.error} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setRemoving(null)}>
            {t("org.cancel")}
          </Button>
          <Button
            className="bg-danger text-white hover:bg-danger/90"
            disabled={send.isPending}
            onClick={() => removing && send.mutate({ method: "delete", path: `${config.path}/${removing.id}` }, { onSuccess: () => setRemoving(null) })}
          >
            {t("common.delete")}
          </Button>
        </div>
      </Modal>
    </section>
  );
}
