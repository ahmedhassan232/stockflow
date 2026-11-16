import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface ServiceRow {
  label: string;
  value: string;
  tone?: "success" | "danger";
}

interface Props {
  icon: LucideIcon;
  title: string;
  ok: boolean;
  detail?: string | null;
  rows: ServiceRow[];
}

export function ServiceCard({ icon: Icon, title, ok, detail, rows }: Props) {
  const { t } = useTranslation();
  return (
    <Card data-testid="service-card" data-status={ok ? "ok" : "error"}>
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <CardTitle className="truncate">{title}</CardTitle>
        </div>
        <Badge tone={ok ? "success" : "danger"}>
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {ok ? t("status.operational") : t("status.down")}
        </Badge>
      </CardHeader>
      <CardContent>
        {detail && !ok ? <p className="mb-3 text-sm text-danger">{detail}</p> : null}
        <dl className="divide-y text-sm">
          {rows.map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-4 py-2">
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd
                className={
                  row.tone === "success"
                    ? "font-medium text-success"
                    : row.tone === "danger"
                      ? "font-medium text-danger"
                      : "font-medium"
                }
              >
                <bdi>{row.value}</bdi>
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
