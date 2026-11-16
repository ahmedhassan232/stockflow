import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/input";
import { login } from "@/features/auth/api";
import { AuthHeading, FormError } from "@/layouts/AuthLayout";
import { errorMessage } from "@/utils/errors";

const schema = z.object({
  email: z.string().min(1, "validation.required").email("validation.email"),
  password: z.string().min(1, "validation.required"),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(schema) });
  const { errors, isSubmitting } = formState;

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const me = await login(values.email, values.password);
      navigate(me.active_company ? (from ?? "/app") : "/select-company", { replace: true });
    } catch (err) {
      setError(errorMessage(err, t));
    }
  });

  return (
    <>
      <AuthHeading title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")} />
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <FormError message={error} />
        <TextField
          label={t("auth.email")}
          type="email"
          autoComplete="username"
          dir="ltr"
          error={errors.email?.message && t(errors.email.message)}
          {...register("email")}
        />
        <TextField
          label={t("auth.password")}
          type="password"
          autoComplete="current-password"
          dir="ltr"
          error={errors.password?.message && t(errors.password.message)}
          {...register("password")}
        />
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? t("auth.signingIn") : t("auth.signIn")}
        </Button>
      </form>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-sm">
        <Link to="/forgot-password" className="text-secondary hover:underline">
          {t("auth.forgot")}
        </Link>
        <span className="text-muted-foreground">
          {t("auth.noAccount")}{" "}
          <Link to="/register" className="font-medium text-secondary hover:underline">
            {t("auth.createAccount")}
          </Link>
        </span>
      </div>
    </>
  );
}
