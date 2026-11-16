import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/input";
import { forgotPassword, resetPassword } from "@/features/auth/api";
import { AuthHeading, FormError } from "@/layouts/AuthLayout";
import { errorMessage } from "@/utils/errors";

function BackToLogin() {
  const { t } = useTranslation();
  return (
    <p className="mt-5 text-center text-sm">
      <Link to="/login" className="font-medium text-secondary hover:underline">
        {t("auth.backToLogin")}
      </Link>
    </p>
  );
}

function Notice({ children }: { children: string }) {
  return (
    <p role="status" className="rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
      {children}
    </p>
  );
}

const forgotSchema = z.object({ email: z.string().min(1, "validation.required").email("validation.email") });

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof forgotSchema>>({
    resolver: zodResolver(forgotSchema),
  });
  const onSubmit = handleSubmit(async ({ email }) => {
    setError(null);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(errorMessage(err, t));
    }
  });
  return (
    <>
      <AuthHeading title={t("auth.forgotTitle")} subtitle={t("auth.forgotSubtitle")} />
      {sent ? (
        <Notice>{t("auth.forgotSent")}</Notice>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <FormError message={error} />
          <TextField
            label={t("auth.email")}
            type="email"
            dir="ltr"
            autoComplete="username"
            error={formState.errors.email?.message && t(formState.errors.email.message)}
            {...register("email")}
          />
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
            {t("auth.sendLink")}
          </Button>
        </form>
      )}
      <BackToLogin />
    </>
  );
}

const resetSchema = z.object({ password: z.string().min(10, "validation.passwordMin") });

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const token = useSearchParams()[0].get("token");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof resetSchema>>({
    resolver: zodResolver(resetSchema),
  });
  const onSubmit = handleSubmit(async ({ password }) => {
    setError(null);
    try {
      await resetPassword(token ?? "", password);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, t));
    }
  });
  return (
    <>
      <AuthHeading title={t("auth.resetTitle")} />
      {!token ? (
        <FormError message={t("auth.resetMissing")} />
      ) : done ? (
        <Notice>{t("auth.resetDone")}</Notice>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <FormError message={error} />
          <TextField
            label={t("auth.newPassword")}
            type="password"
            dir="ltr"
            autoComplete="new-password"
            hint={t("auth.passwordHint")}
            error={formState.errors.password?.message && t(formState.errors.password.message)}
            {...register("password")}
          />
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
            {t("auth.savePassword")}
          </Button>
        </form>
      )}
      <BackToLogin />
    </>
  );
}
