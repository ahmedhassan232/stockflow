import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <p className="text-5xl font-bold text-secondary">404</p>
      <h1 className="mt-3 text-xl font-semibold">{t("common.notFoundTitle")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("common.notFoundBody")}</p>
      <Link
        to="/"
        className="mt-6 inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        {t("common.backHome")}
      </Link>
    </div>
  );
}
