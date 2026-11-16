import { Languages, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router-dom";
import { Logo } from "@/components/common/Logo";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/useTheme";

export function PublicLayout() {
  const { t, i18n } = useTranslation();
  const { theme, toggle } = useTheme();
  const nextLang = i18n.language === "ar" ? "en" : "ar";

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 border-b bg-card/90 backdrop-blur">
        <div className="container flex h-16 items-center justify-between gap-3">
          <Link to="/app" className="rounded-md" aria-label={t("app.name")}>
            <Logo />
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void i18n.changeLanguage(nextLang)}
              aria-label={t("common.switchLanguage")}
            >
              <Languages />
              <span lang={nextLang}>{t("common.language")}</span>
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="size-9"
              onClick={toggle}
              aria-label={theme === "dark" ? t("common.lightMode") : t("common.darkMode")}
            >
              {theme === "dark" ? <Sun /> : <Moon />}
            </Button>
          </div>
        </div>
      </header>
      <main className="container flex-1 py-8 sm:py-10">
        <Outlet />
      </main>
      <footer className="border-t py-5 text-center text-xs text-muted-foreground">
        {t("app.name")} · {t("status.phase")}
      </footer>
    </div>
  );
}
