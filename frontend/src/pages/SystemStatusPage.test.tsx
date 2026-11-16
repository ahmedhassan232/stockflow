import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "@/app/routes";
import i18n from "@/i18n";
import { api, ApiError } from "@/services/api";

const live = {
  data: { success: true, data: { status: "ok", service: "StockFlow", version: "0.1.0", environment: "test", time: "2026-11-14T10:00:00Z" } },
};
const readyOk = {
  data: {
    success: true,
    data: {
      status: "ok",
      database: { status: "ok", latency_ms: 2.4, server_version: "17.5", schema_revision: "0001", rls_enforced_for_role: true },
      redis: { status: "ok", latency_ms: 0.8 },
      time: "2026-11-14T10:00:00Z",
    },
  },
};

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: ["/status"] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function mockGet(handler: (url: string) => unknown) {
  return vi.spyOn(api, "get").mockImplementation(((url: string) => {
    try {
      return Promise.resolve(handler(url));
    } catch (e) {
      return Promise.reject(e);
    }
  }) as typeof api.get);
}

describe("SystemStatusPage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("ar");
  });

  it("shows a loading state, then all three services as operational", async () => {
    mockGet((url) => (url === "/health/live" ? live : readyOk));
    renderApp();
    expect(screen.getByTestId("status-loading")).toBeInTheDocument();

    expect(await screen.findByText("جميع الخدمات تعمل بشكل سليم")).toBeInTheDocument();
    const cards = screen.getAllByTestId("service-card");
    expect(cards).toHaveLength(3);
    cards.forEach((c) => expect(c).toHaveAttribute("data-status", "ok"));
    expect(screen.getByText("مفعّل لحساب التشغيل")).toBeInTheDocument();
    expect(screen.getByText("0001")).toBeInTheDocument();
  });

  it("maps a 503 readiness response to per-service status instead of a generic error", async () => {
    mockGet((url) => {
      if (url === "/health/live") return live;
      throw new ApiError("SERVICE_UNAVAILABLE", "down", 503, {
        status: "error",
        database: { status: "error", detail: "Database is unreachable or not migrated" },
        redis: { status: "ok", latency_ms: 1 },
        time: "2026-11-14T10:00:00Z",
      });
    });
    renderApp();

    expect(await screen.findByText("توجد خدمة واحدة أو أكثر متوقفة")).toBeInTheDocument();
    const [apiCard, dbCard, redisCard] = screen.getAllByTestId("service-card");
    expect(apiCard).toHaveAttribute("data-status", "ok");
    expect(dbCard).toHaveAttribute("data-status", "error");
    expect(redisCard).toHaveAttribute("data-status", "ok");
    expect(within(dbCard!).getByText("Database is unreachable or not migrated")).toBeInTheDocument();
  });

  it("shows an error state with a working retry when the API is unreachable", async () => {
    const get = mockGet(() => {
      throw new ApiError("NETWORK_ERROR", "Network Error");
    });
    renderApp();
    // the hook retries once (~1s backoff) before surfacing the error
    expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent("تعذّر الاتصال بالخادم");

    get.mockImplementation(((url: string) => Promise.resolve(url === "/health/live" ? live : readyOk)) as typeof api.get);
    await userEvent.click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    expect(await screen.findByText("جميع الخدمات تعمل بشكل سليم")).toBeInTheDocument();
  });

  it("is Arabic/RTL by default and switches the whole document to English/LTR", async () => {
    mockGet((url) => (url === "/health/live" ? live : readyOk));
    renderApp();
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("حالة النظام");

    await userEvent.click(screen.getByRole("button", { name: "التبديل إلى الإنجليزية" }));
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("System status");
  });
});
