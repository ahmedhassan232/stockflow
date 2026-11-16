import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/services/api";
import type { ApiSuccess } from "@/types/api";

export type ComponentStatus = "ok" | "error";

export interface ComponentHealth {
  status: ComponentStatus;
  latency_ms?: number | null;
  detail?: string | null;
}
export interface DatabaseHealth extends ComponentHealth {
  server_version?: string | null;
  schema_revision?: string | null;
  rls_enforced_for_role?: boolean | null;
}
export interface Readiness {
  status: ComponentStatus;
  database: DatabaseHealth;
  redis: ComponentHealth;
  time: string;
}
export interface Liveness {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  time: string;
}

export interface SystemHealth {
  api: Liveness;
  readiness: Readiness;
}

/**
 * A 503 from /health/ready is a *valid answer* ("a dependency is down") and still
 * carries per-component detail, so it is mapped to data rather than thrown.
 * Only an unreachable API is an error state.
 */
export async function fetchSystemHealth(): Promise<SystemHealth> {
  const live = await api.get<ApiSuccess<Liveness>>("/health/live");
  try {
    const ready = await api.get<ApiSuccess<Readiness>>("/health/ready");
    return { api: live.data.data, readiness: ready.data.data };
  } catch (err) {
    if (err instanceof ApiError && err.status === 503 && err.details) {
      return { api: live.data.data, readiness: err.details as Readiness };
    }
    throw err;
  }
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: fetchSystemHealth,
    refetchInterval: 15_000,
    retry: 1,
  });
}
