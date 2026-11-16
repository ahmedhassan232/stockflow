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
