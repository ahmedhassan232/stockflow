import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Power, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField, TextField } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/auth/store";
import { useOrgList, useSaveOrgItem, type OrgItem, type OrgKind } from "@/features/organization/api";
import { errorMessage } from "@/utils/errors";

const PAGE_SIZE = 10;

const schema = z.object({
  name: z.string().trim().min(1, "validation.required").max(150),
  code: z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9_-]*$/, "validation.code").max(30),
  phone: z.string().trim().max(32).optional(),
  address: z.string().trim().max(500).optional(),
  branch_id: z.string().optional(),
});
type Values = z.infer<typeof schema>;

function ItemForm({ kind, item, onDone }: { kind: OrgKind; item: OrgItem | null; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useSaveOrgItem(kind);
  const branches = useOrgList("branches", { page: 1, page_size: 100 }, kind === "warehouses");
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: item?.name ?? "",
      code: item?.code ?? "",
      phone: item?.phone ?? "",
      address: item?.address ?? "",
      branch_id: item?.branch_id ?? "",
    },
  });
  const { errors } = formState;
  const msg = (m?: string) => (m ? t(m) : undefined);

  const onSubmit = handleSubmit(async (v) => {
    const input = {
      name: v.name,
      address: v.address || null,
      ...(kind === "branches" ? { phone: v.phone || null } : { branch_id: v.branch_id || null }),
      ...(item ? {} : { code: v.code }), // the code is immutable after creation
    };
    await save.mutateAsync({ id: item?.id, input }).then(onDone, () => undefined);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {save.isError ? (
        <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          {errorMessage(save.error, t)}
        </p>
      ) : null}
      <TextField label={t("org.name")} error={msg(errors.name?.message)} {...register("name")} />
      <TextField label={t("org.code")} dir="ltr" disabled={!!item} error={msg(errors.code?.message)} {...register("code")} />
      {kind === "branches" ? (
        <TextField label={t("org.phone")} dir="ltr" inputMode="tel" {...register("phone")} />
      ) : (
        <SelectField label={t("org.branch")} {...register("branch_id")}>
          <option value="">{t("org.noBranch")}</option>
          {branches.data?.items.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </SelectField>
      )}
      <TextField label={t("org.address")} {...register("address")} />
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onDone}>
          {t("org.cancel")}
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? t("org.saving") : t("org.save")}
        </Button>
      </div>
    </form>
  );
}

export function OrgResourcePage({ kind }: { kind: OrgKind }) {
  const { t } = useTranslation();
  const isBranches = kind === "branches";
  const canManage = useCan(isBranches ? "branches.manage" : "warehouses.manage");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<OrgItem | "new" | null>(null);
  const [toggling, setToggling] = useState<OrgItem | null>(null);

  useEffect(() => {
    const id = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [search]);

  const list = useOrgList(kind, { page, page_size: PAGE_SIZE, ...(q ? { q } : {}) });
  const branches = useOrgList("branches", { page: 1, page_size: 100 }, !isBranches);
  const save = useSaveOrgItem(kind);
  const branchName = (id?: string | null) => branches.data?.items.find((b) => b.id === id)?.name ?? t("org.noBranch");
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));

  const title = t(isBranches ? "org.branchesTitle" : "org.warehousesTitle");
  const editTitle = t(
    editing === "new" ? (isBranches ? "org.addBranch" : "org.addWarehouse") : isBranches ? "org.editBranch" : "org.editWarehouse",
  );

  return (
    <section aria-labelledby="page-title" className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="page-title" className="text-2xl font-bold tracking-tight">
            {title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t(isBranches ? "org.branchesSubtitle" : "org.warehousesSubtitle")}</p>
        </div>
        {canManage ? (
          <Button onClick={() => setEditing("new")}>
            <Plus />
            {t(isBranches ? "org.addBranch" : "org.addWarehouse")}
          </Button>
        ) : null}
      </div>

      <Card>
        <div className="border-b p-3">
          <label className="relative block max-w-sm">
            <span className="sr-only">{t("org.search")}</span>
            <Search className="pointer-events-none absolute start-3 top-3 size-4 text-muted-foreground" aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("org.search")}
              className="h-10 w-full rounded-md border bg-card pe-3 ps-9 text-sm placeholder:text-muted-foreground"
            />
          </label>
        </div>

        {list.isPending ? (
          <div className="space-y-2 p-4" aria-busy="true" data-testid="list-loading">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : list.isError ? (
          <div role="alert" className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm text-danger">{errorMessage(list.error, t)}</p>
            <Button variant="outline" onClick={() => void list.refetch()}>
              {t("common.retry")}
            </Button>
          </div>
        ) : list.data.items.length === 0 ? (
          <p className="p-10 text-center text-sm text-muted-foreground">{t(isBranches ? "org.emptyBranches" : "org.emptyWarehouses")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 text-start font-medium">{t("org.name")}</th>
                  <th scope="col" className="px-4 py-3 text-start font-medium">{t("org.code")}</th>
                  <th scope="col" className="px-4 py-3 text-start font-medium">{t(isBranches ? "org.phone" : "org.branch")}</th>
                  <th scope="col" className="px-4 py-3 text-start font-medium">{t("org.status")}</th>
                  {canManage ? <th scope="col" className="px-4 py-3 text-end font-medium">{t("org.actions")}</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y">
                {list.data.items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-3 font-medium">{item.name}</td>
                    <td className="px-4 py-3"><bdi className="font-mono text-xs">{item.code}</bdi></td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {isBranches ? <bdi>{item.phone ?? "—"}</bdi> : branchName(item.branch_id)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={item.is_active ? "success" : "neutral"}>{t(item.is_active ? "org.active" : "org.inactiveStatus")}</Badge>
                    </td>
                    {canManage ? (
                      <td className="px-4 py-2 text-end">
                        <Button variant="ghost" size="sm" onClick={() => setEditing(item)}>
                          <Pencil />
                          {t("org.edit")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={save.isPending}
                          onClick={() => (item.is_active ? setToggling(item) : save.mutate({ id: item.id, input: { is_active: true } }))}
                        >
                          <Power />
                          {t(item.is_active ? "org.deactivate" : "org.activate")}
                        </Button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {list.data && list.data.total > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-3 text-sm text-muted-foreground">
            <span>{t("org.total", { total: list.data.total })}</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("org.prev")}
              </Button>
              <span>{t("org.pageOf", { page, pages })}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                {t("org.next")}
              </Button>
            </div>
          </div>
        ) : null}
      </Card>

      <Modal open={editing !== null} title={editTitle} closeLabel={t("org.close")} onClose={() => setEditing(null)}>
        {editing !== null ? (
          <ItemForm key={editing === "new" ? "new" : editing.id} kind={kind} item={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        ) : null}
      </Modal>

      <Modal open={toggling !== null} title={t("org.deactivate")} closeLabel={t("org.close")} onClose={() => setToggling(null)}>
        <p className="text-sm">{t("org.confirmDeactivate", { name: toggling?.name ?? "" })}</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setToggling(null)}>
            {t("org.cancel")}
          </Button>
          <Button
            className="bg-danger text-white hover:bg-danger/90"
            onClick={() => {
              if (toggling) save.mutate({ id: toggling.id, input: { is_active: false } });
              setToggling(null);
            }}
          >
            {t("org.deactivate")}
          </Button>
        </div>
      </Modal>
    </section>
  );
}
