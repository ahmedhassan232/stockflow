import { MailWarning } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/features/auth/store";
import { api } from "@/services/api";

export function VerifyEmailBanner() {
  const { t } = useTranslation();
  const user = useAuth((s) => s.me?.user);
  const [state, setState] = useState<"idle" | "busy" | "sent" | "failed">("idle");
  if (!user || user.email_verified) return null;
  const resend = () => {
    setState("busy");
    api.post("/auth/resend-verification").then(() => setState("sent"), () => setState("failed"));
  };
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-warning/30 bg-warning/10 px-4 py-2 text-sm print:hidden">
      <MailWarning className="size-4 shrink-0 text-warning" aria-hidden="true" />
      <span>
        {t("verify.banner")} <bdi className="font-medium">{user.email}</bdi>
      </span>
      {state === "sent" ? (
        <span className="text-success">{t("verify.sent")}</span>
      ) : (
        <button type="button" className="font-medium text-secondary hover:underline disabled:opacity-50" disabled={state === "busy"} onClick={resend}>
          {t(state === "failed" ? "verify.retry" : "verify.resend")}
        </button>
      )}
    </div>
  );
}
