import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { ApiSuccess } from "@/types/api";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export type Params = Record<string, string | number | boolean | undefined | null>;

const clean = (params?: Params) =>
  Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== ""));

/** Query keys start with the resource root ("/products/x" → "products") so one
 *  invalidation refreshes every list and detail of that resource. */
const root = (path: string) => path.split("/")[1] ?? path;

export function useList<T>(path: string, params?: Params, enabled = true) {
  const p = clean(params);
  return useQuery({
    queryKey: [root(path), path, p],
    queryFn: async () => (await api.get<ApiSuccess<Page<T>>>(path, { params: p })).data.data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useGet<T>(path: string, params?: Params, enabled = true, refetchInterval?: number) {
  const p = clean(params);
  return useQuery({
    queryKey: [root(path), path, p],
    queryFn: async () => (await api.get<ApiSuccess<T>>(path, { params: p })).data.data,
    enabled,
    refetchInterval,
  });
}

interface SendArgs {
  method?: "post" | "patch" | "put" | "delete";
  path: string;
  body?: unknown;
  /** Sent as Idempotency-Key: a retried request is executed at most once. */
  idempotencyKey?: string;
}

/** Generic write. `invalidate` lists resource roots whose cached data becomes stale. */
export function useSend<T = unknown>(invalidate: string[]) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ method = "post", path, body, idempotencyKey }: SendArgs) => {
      const res = await api.request<ApiSuccess<T>>({
        method,
        url: path,
        data: body,
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
      return res.data.data;
    },
    onSuccess: () => Promise.all(invalidate.map((key) => client.invalidateQueries({ queryKey: [key] }))),
  });
}

export const newKey = () => crypto.randomUUID();
