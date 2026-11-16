import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/input";
import { registerCompany } from "@/features/auth/api";
import { AuthHeading, FormError } from "@/layouts/AuthLayout";
import { errorMessage } from "@/utils/errors";

// Mirrors backend rules; the backend validates again and is authoritative.
const schema = z.object({
  full_name: z.string().trim().min(2, "validation.nameMin"),
  email: z.string().min(1, "validation.required").email("validation.email"),
  password: z.string().min(10, "validation.passwordMin"),
  company_name: z.string().trim().min(2, "validation.nameMin"),
  company_slug: z.string().trim().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "validation.slug").min(3, "validation.slug"),
});
type Values = z.infer<typeof schema>;

export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(schema) });
  const { errors, isSubmitting } = formState;
  const msg = (m?: string) => (m ? t(m) : undefined);

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await registerCompany({
        full_name: v.full_name,
        email: v.email,
        password: v.password,
        company: { name: v.company_name, slug: v.company_slug },
      });
      navigate("/app", { replace: true });
    } catch (err) {
      setError(errorMessage(err, t));
    }
  });

  return (
    <>
      <AuthHeading title={t("auth.registerTitle")} subtitle={t("auth.registerSubtitle")} />
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <FormError message={error} />
        <TextField label={t("auth.fullName")} autoComplete="name" error={msg(errors.full_name?.message)} {...register("full_name")} />
        <TextField label={t("auth.email")} type="email" autoComplete="username" dir="ltr" error={msg(errors.email?.message)} {...register("email")} />
        <TextField
          label={t("auth.password")}
          type="password"
          autoComplete="new-password"
          dir="ltr"
          hint={t("auth.passwordHint")}
          error={msg(errors.password?.message)}
          {...register("password")}
        />
        <TextField label={t("auth.companyName")} autoComplete="organization" error={msg(errors.company_name?.message)} {...register("company_name")} />
        <TextField label={t("auth.companySlug")} dir="ltr" hint={t("auth.slugHint")} error={msg(errors.company_slug?.message)} {...register("company_slug")} />
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? t("auth.registering") : t("auth.register")}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        {t("auth.haveAccount")}{" "}
        <Link to="/login" className="font-medium text-secondary hover:underline">
          {t("auth.signIn")}
        </Link>
      </p>
    </>
  );
}
