import { create } from "zustand";
import type { Me } from "./types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: Status;
  /** Access token lives in memory only – never in localStorage. */
  accessToken: string | null;
  me: Me | null;
  setToken: (token: string) => void;
  setMe: (me: Me) => void;
  signOut: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  status: "loading",
  accessToken: null,
  me: null,
  setToken: (accessToken) => set({ accessToken }),
  setMe: (me) => set({ me, status: "authenticated" }),
  signOut: () => set({ accessToken: null, me: null, status: "anonymous" }),
}));

/** UI convenience only. The backend re-checks every permission on every request. */
export function useCan(permission: string): boolean {
  return useAuth((s) => s.me?.active_company?.permissions.includes(permission) ?? false);
}
