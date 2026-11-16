import { Building2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { logout, selectCompany } from "@/features/auth/api";
import { useAuth } from "@/features/auth/store";
import { AuthHeading, FormError } from "@/layouts/AuthLayout";
import { errorMessage } from "@/utils/errors";

export function SelectCompanyPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const memberships = useAuth((s) => s.me?.memberships ?? []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = async (tenantId: string) => {
    setBusy(tenantId);
    setError(null);
    try {
      await selectCompany(tenantId);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <AuthHeading title={t("auth.selectTitle")} subtitle={t("auth.selectSubtitle")} />
      <FormError message={error} />
      {memberships.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("auth.noCompanies")}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {memberships.map((m) => {
            const usable = m.tenant_status === "active" && m.membership_status === "active";
            return (
              <li key={m.tenant_id}>
                <button
                  type="button"
                  disabled={!usable || busy !== null}
                  onClick={() => void choose(m.tenant_id)}
                  className="flex w-full items-center gap-3 rounded-md border p-3 text-start hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Building2 className="size-5 shrink-0 text-secondary" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{m.tenant_name}</span>
                    <span className="block truncate text-xs text-muted-foreground" dir="ltr">
                      {m.tenant_slug}
                    </span>
                  </span>
                  {!usable ? (
                    <Badge tone="warning">{m.tenant_status !== "active" ? t("auth.suspended") : t("auth.inactive")}</Badge>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <Button variant="ghost" className="mt-5 w-full" onClick={() => void logout()}>
        {t("nav.logout")}
      </Button>
    </>
  );
}
