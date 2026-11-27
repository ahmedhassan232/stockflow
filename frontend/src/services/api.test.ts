import axios, { AxiosError, type AxiosResponse } from "axios";
import { afterEach, expect, it, vi } from "vitest";
import { ensureBackendReady } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

it("stops retrying when the hosting gate reports an asleep backend", async () => {
  const error = new AxiosError("App asleep");
  error.response = {
    data: {},
    status: 503,
    statusText: "Service Unavailable",
    headers: { "x-blitz-gate": "asleep" },
    config: { headers: {} },
  } as AxiosResponse;

  const request = vi.spyOn(axios, "get").mockRejectedValue(error);

  await expect(ensureBackendReady()).rejects.toMatchObject({
    code: "BACKEND_ASLEEP",
    status: 503,
  });
  expect(request).toHaveBeenCalledTimes(1);
});
