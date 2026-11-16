import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { fetchMe } from "@/features/auth/api";
import { useAuth } from "@/features/auth/store";
import { api } from "@/services/api";

/** Opened from the confirmation e-mail. Works whether or not the person is signed in. */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const started = useRef(false);
  useEffect(() => {
    if (!token || started.current) return; // the link is single-use: never send it twice
    started.current = true;
    api
      .post("/auth/verify-email", { token })
      .then(() => {
        setState("done");
        if (useAuth.getState().status === "authenticated") void fetchMe();
      })
      .catch(() => setState("failed"));
  }, [token]);
  return (
    <main className="mx-auto grid min-h-[60vh] max-w-md place-items-center p-6 text-center">
      <div>
        <h1 className="text-xl font-bold">{t("verify.title")}</h1>
        <p role="status" className={`mt-3 text-sm ${state === "failed" ? "text-danger" : state === "done" ? "text-success" : "text-muted-foreground"}`}>
          {t(state === "working" ? "common.loading" : state === "done" ? "verify.done" : "verify.failed")}
        </p>
        {state !== "working" ? (
          <Link to="/app" className="mt-5 inline-block text-sm font-medium text-secondary hover:underline">{t("verify.continue")}</Link>
        ) : null}
      </div>
    </main>
  );
}
