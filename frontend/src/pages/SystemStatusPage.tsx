import { CircleAlert, CircleCheck, Database, RefreshCw, Server, ServerCrash, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSystemHealth } from "@/features/system/api/health";
import { ServiceCard, type ServiceRow } from "@/features/system/components/ServiceCard";
import { cn } from "@/utils/cn";
import { formatNumber, formatTime } from "@/utils/format";

export function SystemStatusPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { data, isPending, isError, isFetching, refetch } = useSystemHealth();

  const latency = (ms?: number | null): ServiceRow[] =>
    ms == null ? [] : [{ label: t("status.latency"), value: t("status.ms", { value: formatNumber(ms, lang) }) }];

  return (
    <section aria-labelledby="status-title" className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 id="status-title" className="text-2xl font-bold tracking-tight sm:text-3xl">
            {t("status.title")}
          </h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">{t("status.subtitle")}</p>
        </div>
        <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCw className={cn(isFetching && "animate-spin")} />
          {t("common.refresh")}
        </Button>
      </div>

      {isPending ? (
        <div className="grid gap-4 md:grid-cols-3" aria-busy="true" data-testid="status-loading">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : isError || !data ? (
        <Card role="alert" className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <ServerCrash className="size-10 text-danger" aria-hidden="true" />
          <h2 className="text-lg font-semibold">{t("status.unreachableTitle")}</h2>
          <p className="max-w-md text-sm text-muted-foreground">{t("status.unreachableBody")}</p>
          <Button onClick={() => void refetch()} disabled={isFetching}>
            {t("common.retry")}
          </Button>
        </Card>
      ) : (
        <>
          <div
            role="status"
            className={cn(
              "mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border px-4 py-3 text-sm font-medium",
              data.readiness.status === "ok"
                ? "border-success/30 bg-success/10 text-success"
                : "border-danger/30 bg-danger/10 text-danger",
            )}
          >
            <span className="flex items-center gap-2">
              {data.readiness.status === "ok" ? (
                <CircleCheck className="size-5" aria-hidden="true" />
              ) : (
                <CircleAlert className="size-5" aria-hidden="true" />
              )}
              {data.readiness.status === "ok" ? t("status.allOk") : t("status.degraded")}
            </span>
            <span className="text-xs font-normal text-muted-foreground">
              {t("status.lastChecked", { time: formatTime(data.readiness.time, lang) })}
            </span>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <ServiceCard
              icon={Server}
              title={t("status.api")}
              ok
              rows={[
                { label: t("status.version"), value: data.api.version },
                { label: t("status.environment"), value: data.api.environment },
              ]}
            />
            <ServiceCard
              icon={Database}
              title={t("status.database")}
              ok={data.readiness.database.status === "ok"}
              detail={data.readiness.database.detail}
              rows={[
                ...(data.readiness.database.server_version
                  ? [{ label: t("status.version"), value: data.readiness.database.server_version }]
                  : []),
                ...(data.readiness.database.schema_revision
                  ? [{ label: t("status.schemaRevision"), value: data.readiness.database.schema_revision }]
                  : []),
                ...(data.readiness.database.rls_enforced_for_role == null
                  ? []
                  : [
                      {
                        label: t("status.rls"),
                        value: data.readiness.database.rls_enforced_for_role
                          ? t("status.rlsEnforced")
                          : t("status.rlsBypassable"),
                        tone: data.readiness.database.rls_enforced_for_role
                          ? ("success" as const)
                          : ("danger" as const),
                      },
                    ]),
                ...latency(data.readiness.database.latency_ms),
              ]}
            />
            <ServiceCard
              icon={Zap}
              title={t("status.redis")}
              ok={data.readiness.redis.status === "ok"}
              detail={data.readiness.redis.detail}
              rows={latency(data.readiness.redis.latency_ms)}
            />
          </div>
        </>
      )}
    </section>
  );
}
