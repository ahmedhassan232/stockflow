import axios from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "@/app/routes";
import i18n from "@/i18n";
import { api, ApiError } from "@/services/api";
import { useAuth } from "./store";
import type { Me } from "./types";

function me(permissions: string[], extra: Partial<Me> = {}): Me {
  return {
    user: { id: "u1", full_name: "سارة علي", email: "sara@example.com", phone: null, avatar_url: null, email_verified: true },
    memberships: [{ tenant_id: "t1", tenant_name: "النيل", tenant_slug: "nile", tenant_status: "active", membership_status: "active" }],
    active_company: {
      tenant_id: "t1", name: "النيل", slug: "nile", currency: "EGP", timezone: "Africa/Cairo",
      role_code: "x", role_name: "Role", permissions, restricted_to_branches: false, branch_ids: [],
    },
    ...extra,
  };
}

const emptyPage = { data: { success: true, data: { items: [], total: 0, page: 1, page_size: 10 } } };

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("authentication UI", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    vi.spyOn(axios, "get").mockResolvedValue({} as never);
    useAuth.setState({ status: "anonymous", accessToken: null, me: null });
    await i18n.changeLanguage("ar");
  });

  it("redirects anonymous visitors from protected routes to the login page", async () => {
    const router = renderAt("/app/branches");
    expect(await screen.findByRole("heading", { name: "تسجيل الدخول" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("validates the login form on the client before calling the API", async () => {
    const post = vi.spyOn(api, "post");
    renderAt("/login");
    await userEvent.click(screen.getByRole("button", { name: "دخول" }));
    expect(await screen.findAllByText("هذا الحقل مطلوب")).toHaveLength(2);

    await userEvent.type(screen.getByLabelText("البريد الإلكتروني"), "not-an-email");
    await userEvent.type(screen.getByLabelText("كلمة المرور"), "x");
    await userEvent.click(screen.getByRole("button", { name: "دخول" }));
    expect(await screen.findByText("اكتب بريدًا إلكترونيًا صحيحًا")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the backend's rejection in the user's language and stays on the page", async () => {
    vi.spyOn(api, "post").mockRejectedValue(new ApiError("INVALID_CREDENTIALS", "Invalid email or password", 401));
    const router = renderAt("/login");
    await userEvent.type(screen.getByLabelText("البريد الإلكتروني"), "sara@example.com");
    await userEvent.type(screen.getByLabelText("كلمة المرور"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "دخول" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
    expect(router.state.location.pathname).toBe("/login");
    expect(useAuth.getState().status).toBe("anonymous");
  });

  it("signs in, keeps the token in memory only, and lands in the app", async () => {
    vi.spyOn(api, "post").mockResolvedValue({ data: { success: true, data: { access_token: "tok-123" } } });
    vi.spyOn(api, "get").mockImplementation(((url: string) =>
      Promise.resolve(url === "/auth/me" ? { data: { success: true, data: me(["branches.view"]) } } : emptyPage)) as typeof api.get);
    const router = renderAt("/login");
    await userEvent.type(screen.getByLabelText("البريد الإلكتروني"), "sara@example.com");
    await userEvent.type(screen.getByLabelText("كلمة المرور"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "دخول" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/app"));
    expect(useAuth.getState().accessToken).toBe("tok-123");
    expect(JSON.stringify({ ...localStorage })).not.toContain("tok-123");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("tok-123");
  });

  it("sends users without a selected company to the company chooser", async () => {
    useAuth.setState({ status: "authenticated", accessToken: "t", me: me([], { active_company: null }) });
    const router = renderAt("/app");
    expect(await screen.findByRole("heading", { name: "اختر الشركة" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/select-company");
  });

  it("shows only the navigation and actions the role is permitted to use", async () => {
    vi.spyOn(api, "get").mockResolvedValue(emptyPage);
    useAuth.setState({ status: "authenticated", accessToken: "t", me: me(["branches.view"]) });
    renderAt("/app/branches");
    const nav = await screen.findByRole("navigation");
    expect(nav).toHaveTextContent("الفروع");
    expect(nav).not.toHaveTextContent("المخازن");
    expect(await screen.findByText("لا توجد فروع مطابقة.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "إضافة فرع" })).not.toBeInTheDocument();
  });

  it("offers management actions when the role has the manage permission", async () => {
    vi.spyOn(api, "get").mockResolvedValue(emptyPage);
    useAuth.setState({ status: "authenticated", accessToken: "t", me: me(["branches.view", "branches.manage", "warehouses.view"]) });
    renderAt("/app/branches");
    expect(await screen.findByRole("button", { name: "إضافة فرع" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toHaveTextContent("المخازن");
  });
});
