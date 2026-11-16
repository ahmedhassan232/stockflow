import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/features/auth/store";
import "@/i18n";

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5_000, retry: 1 } } }),
  );
  // Cached data belongs to ONE company session. Drop all of it on sign-out or when the
  // active company changes, so nothing from the previous company can be displayed.
  useEffect(
    () =>
      useAuth.subscribe((state, previous) => {
        const before = previous.me?.active_company?.tenant_id;
        const after = state.me?.active_company?.tenant_id;
        if (before && before !== after) client.clear();
      }),
    [client],
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
