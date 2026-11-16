import { useTranslation } from "react-i18next";
import { CrudPage, type CrudConfig, type Field } from "@/components/common/CrudPage";
import { useAuth } from "@/features/auth/store";
import { useList } from "@/features/data/api";
import type { Named, Party, Product } from "@/features/data/types";
import { formatMoney } from "@/utils/format";

type Row<T> = T & Record<string, unknown>;

const partyFields: Field[] = [
  { name: "name", label: "fields.name", required: true },
  { name: "phone", label: "fields.phone", type: "tel" },
  { name: "email", label: "fields.email", type: "email" },
  { name: "tax_number", label: "fields.taxNumber", ltr: true },
  { name: "address", label: "fields.address" },
  { name: "notes", label: "fields.notes" },
];

function partyConfig(kind: "suppliers" | "customers"): CrudConfig<Row<Party>> {
  return {
    path: `/${kind}`,
    title: `${kind}.title`,
    subtitle: `${kind}.subtitle`,
    addLabel: `${kind}.add`,
    empty: `${kind}.empty`,
    managePermission: `${kind}.manage`,
    fields: partyFields,
    columns: [
      { key: "name", header: "fields.name", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "phone", header: "fields.phone", render: (r) => <bdi>{r.phone ?? "—"}</bdi> },
      { key: "email", header: "fields.email", render: (r) => <bdi>{r.email ?? "—"}</bdi> },
    ],
  };
}

function useTranslatedHeaders<T>(config: CrudConfig<T>): CrudConfig<T> {
  const { t } = useTranslation();
  return { ...config, columns: config.columns.map((c) => ({ ...c, header: t(c.header) })) };
}

export function SuppliersPage() {
  return <CrudPage config={useTranslatedHeaders(partyConfig("suppliers"))} />;
}
export function CustomersPage() {
  return <CrudPage config={useTranslatedHeaders(partyConfig("customers"))} />;
}

export function CategoriesPage() {
  const config: CrudConfig<Row<Named & { description: string | null }>> = {
    path: "/categories",
    title: "categories.title",
    subtitle: "categories.subtitle",
    addLabel: "categories.add",
    empty: "categories.empty",
    managePermission: "categories.manage",
    alsoInvalidate: ["products"],
    fields: [
      { name: "name", label: "fields.name", required: true },
      { name: "description", label: "fields.description" },
    ],
    columns: [
      { key: "name", header: "fields.name", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "description", header: "fields.description", render: (r) => <span className="text-muted-foreground">{r.description ?? "—"}</span> },
    ],
  };
  return <CrudPage config={useTranslatedHeaders(config)} />;
}

export function UnitsPage() {
  const config: CrudConfig<Row<Named & { abbreviation: string }>> = {
    path: "/units",
    title: "units.title",
    subtitle: "units.subtitle",
    addLabel: "units.add",
    empty: "units.empty",
    managePermission: "categories.manage",
    alsoInvalidate: ["products"],
    fields: [
      { name: "name", label: "fields.name", required: true },
      { name: "abbreviation", label: "units.abbreviation", required: true },
    ],
    columns: [
      { key: "name", header: "fields.name", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "abbreviation", header: "units.abbreviation", render: (r) => r.abbreviation },
    ],
  };
  return <CrudPage config={useTranslatedHeaders(config)} />;
}

export function ProductsPage() {
  const { i18n } = useTranslation();
  const currency = useAuth((s) => s.me?.active_company?.currency ?? "EGP");
  const categories = useList<Named>("/categories", { page_size: 100 });
  const categoryName = (id: string | null) => categories.data?.items.find((c) => c.id === id)?.name ?? "—";
  const config: CrudConfig<Row<Product>> = {
    path: "/products",
    title: "products.title",
    subtitle: "products.subtitle",
    addLabel: "products.add",
    empty: "products.empty",
    managePermission: { create: "products.create", update: "products.update", remove: "products.delete" },
    canDelete: true,
    alsoInvalidate: ["inventory"],
    fields: [
      { name: "name", label: "fields.name", required: true },
      { name: "sku", label: "products.sku", required: true, ltr: true, createOnly: true, hint: "products.skuHint" },
      { name: "barcode", label: "products.barcode", ltr: true },
      { name: "category_id", label: "products.category", type: "select", optionsPath: "/categories" },
      { name: "unit_id", label: "products.unit", type: "select", optionsPath: "/units" },
      { name: "selling_price", label: "products.sellingPrice", type: "decimal", places: 2, required: true, defaultValue: "0" },
      { name: "purchase_price", label: "products.purchasePrice", type: "decimal", places: 4, defaultValue: "0" },
      { name: "tax_rate", label: "products.taxRate", type: "decimal", places: 2, max: 100, defaultValue: "0" },
      { name: "description", label: "fields.description" },
      { name: "track_inventory", label: "products.trackInventory", type: "checkbox", defaultValue: true, createOnly: true },
    ],
    columns: [
      {
        key: "name",
        header: "fields.name",
        render: (r) => (
          <>
            <span className="font-medium">{r.name}</span>
            <bdi className="block font-mono text-xs text-muted-foreground">{r.sku}</bdi>
          </>
        ),
      },
      { key: "category", header: "products.category", render: (r) => categoryName(r.category_id) },
      { key: "price", header: "products.sellingPrice", align: "end", render: (r) => <bdi className="tabular-nums">{formatMoney(r.selling_price, currency, i18n.language)}</bdi> },
      { key: "cost", header: "products.averageCost", align: "end", render: (r) => <bdi className="tabular-nums text-muted-foreground">{formatMoney(r.average_cost, currency, i18n.language)}</bdi> },
    ],
  };
  return <CrudPage config={useTranslatedHeaders(config)} />;
}
