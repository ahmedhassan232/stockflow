import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuth } from "@/features/auth/store";
import type { AuthPayload } from "@/features/auth/types";
import type { ApiFailure, ApiSuccess } from "@/types/api";

/** Same-origin by default; proxied to the backend by Vite (dev) or nginx. */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  timeout: 15_000,
  withCredentials: true, // sends the HttpOnly refresh cookie to /auth/* only (cookie Path)
  headers: { Accept: "application/json" },
});

export class ApiError<D = unknown> extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
    public readonly details?: D,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof AxiosError) {
    const body = err.response?.data as ApiFailure | undefined;
    if (body && body.success === false && body.error) {
      return new ApiError(body.error.code, body.error.message, err.response?.status, body.error.details);
    }
    if (!err.response) return new ApiError("NETWORK_ERROR", err.message);
    return new ApiError("HTTP_ERROR", err.message, err.response.status);
  }
  return new ApiError("UNKNOWN_ERROR", err instanceof Error ? err.message : "Unknown error");
}

/**
 * Wake a sleeping backend before auth requests.
 *
 * Some hosting plans pause idle services. A readiness request starts the service;
 * bounded retries give it time to become healthy without asking the user to open
 * the health URL manually. Concurrent callers share the same wake-up attempt.
 */
let backendReady: Promise<void> | null = null;

export function ensureBackendReady(): Promise<void> {
  if (!backendReady) {
    backendReady = (async () => {
      const delays = [0, 1_500, 3_000, 5_000, 8_000, 10_000, 10_000];
      let lastError: unknown;

      for (let attempt = 0; attempt < delays.length; attempt += 1) {
        if (delays[attempt] > 0) {
          await new Promise((resolve) => setTimeout(resolve, delays[attempt]));
        }

        try {
          const baseURL = (api.defaults.baseURL ?? "/api/v1").replace(/\/+$/, "");
          await axios.get(`${baseURL}/health/ready`, {
            timeout: 10_000,
            withCredentials: true,
            headers: { Accept: "application/json" },
          });
          return;
        } catch (error) {
          lastError = error;
          const status = error instanceof AxiosError ? error.response?.status : undefined;
          const retryable = status === undefined || [502, 503, 504].includes(status);
          if (!retryable || attempt === delays.length - 1) break;
        }
      }

      throw toApiError(lastError);
    })().finally(() => {
      backendReady = null;
    });
  }

  return backendReady;
}

api.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken;
  if (token) config.headers.set("Authorization", `Bearer ${token}`);
  return config;
});

let refreshing: Promise<AuthPayload> | null = null;

/** Single-flight: concurrent 401s share ONE refresh call (refresh tokens are single-use). */
export function refreshSession(): Promise<AuthPayload> {
  refreshing ??= (async () => {
    try {
      let res;
      try {
        res = await axios.post<ApiSuccess<AuthPayload>>(`${api.defaults.baseURL}/auth/refresh`, null, {
          withCredentials: true,
        });
      } catch (err) {
        // Another tab rotated the token a moment ago: the cookie is already the new one.
        if (toApiError(err).code !== "REFRESH_RACE") throw err;
        res = await axios.post<ApiSuccess<AuthPayload>>(`${api.defaults.baseURL}/auth/refresh`, null, {
          withCredentials: true,
        });
      }
      useAuth.getState().setToken(res.data.data.access_token);
      return res.data.data;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

type Retriable = InternalAxiosRequestConfig & { _retried?: boolean };

api.interceptors.response.use(
  (r) => r,
  async (err: unknown) => {
    const original = (err as AxiosError).config as Retriable | undefined;
    const status = (err as AxiosError).response?.status;
    const isAuthCall = original?.url?.startsWith("/auth/") && original.url !== "/auth/me";
    if (status === 401 && original && !original._retried && !isAuthCall && useAuth.getState().accessToken) {
      original._retried = true;
      try {
        await refreshSession();
        return await api(original);
      } catch {
        useAuth.getState().signOut();
      }
    }
    return Promise.reject(toApiError(err));
  },
);
