import { Navigate, type RouteObject } from "react-router-dom";
import { GuestOnly, RequireAuth } from "@/features/auth/guards";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";
import { PublicLayout } from "@/layouts/PublicLayout";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SystemStatusPage } from "@/pages/SystemStatusPage";
import { OrgResourcePage } from "@/pages/app/OrgResourcePage";
import { PlatformPage } from "@/pages/PlatformPage";
import { DashboardPage } from "@/pages/app/DashboardPage";
import { ExpensesPage } from "@/pages/app/ExpensesPage";
import { InventoryPage } from "@/pages/app/InventoryPage";
import { PosPage } from "@/pages/app/PosPage";
import { PurchasesPage } from "@/pages/app/PurchasesPage";
import { ReportsPage } from "@/pages/app/ReportsPage";
import { SalesPage } from "@/pages/app/SalesPage";
import { AuditLogPage, SettingsPage } from "@/pages/app/SettingsPages";
import { EmployeesPage, RolesPage } from "@/pages/app/TeamPages";
import { CategoriesPage, CustomersPage, ProductsPage, SuppliersPage, UnitsPage } from "@/pages/app/masterData";
import { LoginPage } from "@/pages/auth/LoginPage";
import { ForgotPasswordPage, ResetPasswordPage } from "@/pages/auth/PasswordPages";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { SelectCompanyPage } from "@/pages/auth/SelectCompanyPage";

export const routes: RouteObject[] = [
  { path: "/", element: <Navigate to="/app" replace /> },
  {
    element: <GuestOnly />,
    children: [
      {
        element: <AuthLayout />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/register", element: <RegisterPage /> },
          { path: "/forgot-password", element: <ForgotPasswordPage /> },
          { path: "/reset-password", element: <ResetPasswordPage /> },
        ],
      },
    ],
  },
  {
    element: <RequireAuth needCompany={false} />,
    children: [{ element: <AuthLayout />, children: [{ path: "/select-company", element: <SelectCompanyPage /> }] }],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/app",
        element: <AppLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "pos", element: <PosPage /> },
          { path: "sales", element: <SalesPage /> },
          { path: "customers", element: <CustomersPage /> },
          { path: "products", element: <ProductsPage /> },
          { path: "categories", element: <CategoriesPage /> },
          { path: "units", element: <UnitsPage /> },
          { path: "inventory", element: <InventoryPage /> },
          { path: "purchases", element: <PurchasesPage /> },
          { path: "suppliers", element: <SuppliersPage /> },
          { path: "expenses", element: <ExpensesPage /> },
          { path: "reports", element: <ReportsPage /> },
          { path: "employees", element: <EmployeesPage /> },
          { path: "roles", element: <RolesPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "audit-log", element: <AuditLogPage /> },
          { path: "branches", element: <OrgResourcePage key="branches" kind="branches" /> },
          { path: "warehouses", element: <OrgResourcePage key="warehouses" kind="warehouses" /> },
        ],
      },
    ],
  },
  { element: <RequireAuth needCompany={false} />, children: [{ path: "/platform", element: <PlatformPage /> }] },
  {
    element: <PublicLayout />,
    children: [
      { path: "/verify-email", element: <VerifyEmailPage /> },
      { path: "/status", element: <SystemStatusPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
