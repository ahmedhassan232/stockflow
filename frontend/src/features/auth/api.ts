import { api, refreshSession } from "@/services/api";
import type { ApiSuccess } from "@/types/api";
import { useAuth } from "./store";
import type { AuthPayload, Me } from "./types";

export async function fetchMe(): Promise<Me> {
  const res = await api.get<ApiSuccess<Me>>("/auth/me");
  useAuth.getState().setMe(res.data.data);
  return res.data.data;
}

async function adopt(payload: AuthPayload): Promise<Me> {
  useAuth.getState().setToken(payload.access_token);
  return fetchMe();
}

/** Restores the session from the HttpOnly refresh cookie on page load. */
export async function bootstrapSession(): Promise<void> {
  try {
    await refreshSession();
    await fetchMe();
  } catch {
    useAuth.getState().signOut();
  }
}

export async function login(email: string, password: string): Promise<Me> {
  const res = await api.post<ApiSuccess<AuthPayload>>("/auth/login", { email, password });
  return adopt(res.data.data);
}

export interface RegisterInput {
  full_name: string;
  email: string;
  password: string;
  company: { name: string; slug: string };
}
export async function registerCompany(input: RegisterInput): Promise<Me> {
  const res = await api.post<ApiSuccess<AuthPayload>>("/auth/register", input);
  return adopt(res.data.data);
}

export async function selectCompany(tenantId: string): Promise<Me> {
  const res = await api.post<ApiSuccess<{ access_token: string }>>("/auth/select-company", {
    tenant_id: tenantId,
  });
  useAuth.getState().setToken(res.data.data.access_token);
  return fetchMe();
}

export async function logout(): Promise<void> {
  try {
    await api.post("/auth/logout");
  } finally {
    useAuth.getState().signOut();
  }
}

export async function forgotPassword(email: string): Promise<void> {
  await api.post("/auth/forgot-password", { email });
}

export async function resetPassword(email: string, code: string, new_password: string): Promise<void> {
  await api.post("/auth/reset-password", { email, code, new_password });
}
