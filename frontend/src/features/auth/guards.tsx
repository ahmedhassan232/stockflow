import { useEffect, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { bootstrapSession } from "./api";
import { useAuth } from "./store";

let bootstrapped = false;

export function SessionBootstrap({ children }: { children: ReactNode }) {
  const status = useAuth((s) => s.status);
  useEffect(() => {
    if (!bootstrapped) {
      bootstrapped = true;
      void bootstrapSession();
    }
  }, []);
  if (status === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center p-6" aria-busy="true" data-testid="session-loading">
        <Skeleton className="h-40 w-full max-w-md" />
      </div>
    );
  }
  return <>{children}</>;
}

/** Signed-in area. Without a selected company the user is sent to the company chooser. */
export function RequireAuth({ needCompany = true }: { needCompany?: boolean }) {
  const { status, me } = useAuth();
  const location = useLocation();
  if (status !== "authenticated") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (needCompany && !me?.active_company) return <Navigate to="/select-company" replace />;
  return <Outlet />;
}

export function GuestOnly() {
  const status = useAuth((s) => s.status);
  return status === "authenticated" ? <Navigate to="/app" replace /> : <Outlet />;
}
