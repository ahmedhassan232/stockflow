import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router-dom";
import { Logo } from "@/components/common/Logo";
import { Button } from "@/components/ui/button";

export function AuthLayout() {
  const { t, i18n } = useTranslation();
  const next = i18n.language === "ar" ? "en" : "ar";
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="container flex h-16 items-center justify-between">
        <Link to="/" aria-label={t("app.name")} className="rounded-md">
          <Logo />
        </Link>
        <Button variant="ghost" size="sm" onClick={() => void i18n.changeLanguage(next)} aria-label={t("common.switchLanguage")}>
          <Languages />
          <span lang={next}>{t("common.language")}</span>
        </Button>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-12 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-card sm:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export function AuthHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {subtitle ? <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p> : null}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}
