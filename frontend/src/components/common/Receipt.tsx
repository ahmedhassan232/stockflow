import { Printer } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMoney } from "@/components/common/pickers";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/store";
import type { Sale } from "@/features/data/types";
import { isPositive } from "@/utils/decimal";
import { formatDateTime, formatQty } from "@/utils/format";

/** Printable invoice. Every figure shown is the server's – nothing is recomputed here. */
export function Receipt({ sale, footer }: { sale: Sale; footer?: string | null }) {
  const { t, i18n } = useTranslation();
  const money = useMoney();
  const company = useAuth((s) => s.me?.active_company?.name);
  const rows: [string, string | undefined, boolean?][] = [
    [t("fields.subtotal"), sale.subtotal],
    [t("fields.discount"), isPositive(sale.discount_amount) ? sale.discount_amount : undefined],
    [t("fields.tax"), sale.tax_amount],
    [t("fields.total"), sale.total, true],
    [t("fields.paid"), sale.paid_amount],
    [t("sales.returned"), isPositive(sale.returned_amount) ? sale.returned_amount : undefined],
    [t("fields.balanceDue"), isPositive(sale.balance_due) ? sale.balance_due : undefined],
    [t("pos.change"), sale.change_due && isPositive(sale.change_due) ? sale.change_due : undefined],
  ];
  return (
    <div>
      <div className="print-area space-y-3 text-sm">
        <div className="text-center">
          <p className="text-lg font-bold">{company}</p>
          <p>
            {t("sales.invoice")} <bdi className="font-mono">{sale.number}</bdi>
          </p>
          <p className="text-xs text-muted-foreground">{formatDateTime(sale.created_at, i18n.language)}</p>
          {sale.status === "cancelled" ? <p className="font-bold text-danger">{t("sales.status.cancelled")}</p> : null}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 text-xs">
          {sale.customer_name ? (
            <>
              <dt className="text-muted-foreground">{t("sales.customer")}</dt>
              <dd className="text-end">{sale.customer_name}</dd>
            </>
          ) : null}
          {sale.cashier_name ? (
            <>
              <dt className="text-muted-foreground">{t("sales.cashier")}</dt>
              <dd className="text-end">{sale.cashier_name}</dd>
            </>
          ) : null}
        </dl>
        <table className="w-full border-y text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-1.5 text-start font-medium">{t("fields.product")}</th>
              <th className="py-1.5 text-end font-medium">{t("fields.quantity")}</th>
              <th className="py-1.5 text-end font-medium">{t("fields.price")}</th>
              <th className="py-1.5 text-end font-medium">{t("fields.total")}</th>
            </tr>
          </thead>
          <tbody>
            {(sale.items ?? []).map((i) => (
              <tr key={i.id}>
                <td className="py-1.5">{i.product_name}</td>
                <td className="py-1.5 text-end tabular-nums">{formatQty(i.quantity, i18n.language)}</td>
                <td className="py-1.5 text-end"><bdi className="tabular-nums">{money(i.unit_price)}</bdi></td>
                <td className="py-1.5 text-end"><bdi className="tabular-nums">{money(i.line_total)}</bdi></td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="ms-auto grid max-w-[16rem] grid-cols-2 gap-y-1">
          {rows.map(([label, value, strong]) =>
            value === undefined ? null : (
              <div key={label} className={`col-span-2 flex justify-between ${strong ? "border-t pt-1 text-base font-bold" : ""}`}>
                <dt className={strong ? "" : "text-muted-foreground"}>{label}</dt>
                <dd><bdi className="tabular-nums">{money(value)}</bdi></dd>
              </div>
            ),
          )}
        </dl>
        {footer ? <p className="border-t pt-2 text-center text-xs text-muted-foreground">{footer}</p> : null}
      </div>
      <div className="mt-4 flex justify-end print:hidden">
        <Button variant="outline" onClick={() => window.print()}>
          <Printer />
          {t("sales.print")}
        </Button>
      </div>
    </div>
  );
}
