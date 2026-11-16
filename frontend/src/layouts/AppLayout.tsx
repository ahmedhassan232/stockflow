import { Activity, BarChart3, Boxes, Building2, ClipboardList, Contact, Globe, Wallet, Languages, LayoutDashboard, LogOut, Menu, Moon, Package, Receipt, Ruler, ScrollText, Settings, ShieldCheck, ShoppingCart, Store, Sun, Tags, Truck, Users, Warehouse, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet } from "react-router-dom";
import { Logo } from "@/components/common/Logo";
import { VerifyEmailBanner } from "@/components/common/VerifyEmailBanner";
import { NotificationBell } from "@/components/common/NotificationBell";
import { Button } from "@/components/ui/button";
import { logout } from "@/features/auth/api";
import { useAuth } from "@/features/auth/store";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** shown if the user holds ANY of these (UI only – the API enforces access) */
  permissions?: string[];
  end?: boolean;
}

const NAV: { heading?: string; items: NavItem[] }[] = [
  {
    items: [
      { to: "/app", label: "nav.overview", icon: LayoutDashboard, end: true },
      { to: "/app/pos", label: "nav.pos", icon: ShoppingCart, permissions: ["sales.create"] },
    ],
  },
  {
    heading: "nav.groupSales",
    items: [
      { to: "/app/sales", label: "nav.sales", icon: Receipt, permissions: ["sales.view"] },
      { to: "/app/customers", label: "nav.customers", icon: Contact, permissions: ["customers.view"] },
    ],
  },
  {
    heading: "nav.groupStock",
    items: [
      { to: "/app/products", label: "nav.products", icon: Package, permissions: ["products.view"] },
      { to: "/app/categories", label: "nav.categories", icon: Tags, permissions: ["categories.manage"] },
      { to: "/app/units", label: "nav.units", icon: Ruler, permissions: ["categories.manage"] },
      { to: "/app/inventory", label: "nav.inventory", icon: Boxes, permissions: ["inventory.view"] },
    ],
  },
  {
    heading: "nav.groupPurchasing",
    items: [
      { to: "/app/purchases", label: "nav.purchases", icon: ClipboardList, permissions: ["purchases.view"] },
      { to: "/app/suppliers", label: "nav.suppliers", icon: Truck, permissions: ["suppliers.view"] },
    ],
  },
  {
    heading: "nav.groupManage",
    items: [
      { to: "/app/expenses", label: "nav.expenses", icon: Wallet, permissions: ["expenses.view"] },
      { to: "/app/reports", label: "nav.reports", icon: BarChart3, permissions: ["reports.sales.view", "reports.financial.view"] },
      { to: "/app/branches", label: "nav.branches", icon: Store, permissions: ["branches.view"] },
      { to: "/app/warehouses", label: "nav.warehouses", icon: Warehouse, permissions: ["warehouses.view"] },
      { to: "/app/employees", label: "nav.employees", icon: Users, permissions: ["employees.view"] },
      { to: "/app/roles", label: "nav.roles", icon: ShieldCheck, permissions: ["employees.view"] },
      { to: "/app/settings", label: "nav.settings", icon: Settings, permissions: ["settings.view"] },
      { to: "/app/audit-log", label: "nav.audit", icon: ScrollText, permissions: ["settings.view"] },
      { to: "/status", label: "nav.status", icon: Activity },
    ],
  },
];

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const { theme, toggle } = useTheme();
  const me = useAuth((s) => s.me);
  const [open, setOpen] = useState(false);
  const permissions = me?.active_company?.permissions ?? [];
  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.permissions || i.permissions.some((p) => permissions.includes(p))) })).filter((g) => g.items.length > 0);
  const nextLang = i18n.language === "ar" ? "en" : "ar";
  const multiCompany = (me?.memberships.length ?? 0) > 1;

  return (
    <div className="min-h-dvh lg:flex">
      {open ? <div className="fixed inset-0 z-30 bg-primary/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden="true" /> : null}
      <aside
        className={cn(
          "fixed inset-y-0 start-0 z-40 flex w-64 flex-col border-e bg-card transition-transform print:hidden lg:sticky lg:top-0 lg:h-dvh",
          open ? "translate-x-0" : "max-lg:ltr:-translate-x-full max-lg:rtl:translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between border-b px-4">
          <Link to="/app" className="rounded-md" onClick={() => setOpen(false)}>
            <Logo />
          </Link>
          <button type="button" className="rounded-md p-2 hover:bg-muted lg:hidden" onClick={() => setOpen(false)} aria-label={t("org.close")}>
            <X className="size-4" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-3" aria-label={t("nav.menu")}>
          {groups.map((group, index) => (
            <div key={group.heading ?? index} className="space-y-1">
              {group.heading ? <p className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t(group.heading)}</p> : null}
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                      isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  {t(label)}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t p-3">
          <div className="flex items-center gap-2 px-1 pb-2">
            <Building2 className="size-4 shrink-0 text-secondary" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{me?.active_company?.name}</p>
              <p className="truncate text-xs text-muted-foreground">{me?.user.full_name}</p>
            </div>
          </div>
          {me?.user.is_platform_admin ? (
            <Link to="/platform" className="mb-1 flex items-center gap-2 rounded-md px-3 py-2 text-sm text-secondary hover:bg-muted">
              <Globe className="size-4" aria-hidden="true" />
              {t("platform.title")}
            </Link>
          ) : null}
          {multiCompany ? (
            <Link to="/select-company" className="mb-1 block rounded-md px-3 py-2 text-sm text-secondary hover:bg-muted">
              {t("nav.switchCompany")}
            </Link>
          ) : null}
          <Button variant="ghost" className="w-full justify-start" onClick={() => void logout()}>
            <LogOut className="rtl:-scale-x-100" />
            {t("nav.logout")}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex print:hidden h-16 items-center justify-between gap-2 border-b bg-card/90 px-4 backdrop-blur">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label={t("nav.menu")}>
            <Menu />
          </Button>
          <div className="ms-auto flex items-center gap-2">
            <NotificationBell />
            <Button variant="outline" size="sm" onClick={() => void i18n.changeLanguage(nextLang)} aria-label={t("common.switchLanguage")}>
              <Languages />
              <span lang={nextLang}>{t("common.language")}</span>
            </Button>
            <Button variant="outline" size="icon" className="size-9" onClick={toggle} aria-label={theme === "dark" ? t("common.lightMode") : t("common.darkMode")}>
              {theme === "dark" ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>
        <VerifyEmailBanner />
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
