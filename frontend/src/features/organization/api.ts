import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { ApiSuccess } from "@/types/api";

export type OrgKind = "branches" | "warehouses";

export interface OrgItem {
  id: string;
  name: string;
  code: string;
  address: string | null;
  is_active: boolean;
  phone?: string | null;
  branch_id?: string | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface ListParams {
  page: number;
  page_size: number;
  q?: string;
}

export function useOrgList(kind: OrgKind, params: ListParams, enabled = true) {
  return useQuery({
    queryKey: [kind, params],
    queryFn: async () => (await api.get<ApiSuccess<Page<OrgItem>>>(`/${kind}`, { params })).data.data,
    placeholderData: keepPreviousData, // server-side pagination without flicker
    enabled,
  });
}

export type OrgInput = Partial<Pick<OrgItem, "name" | "code" | "address" | "phone" | "branch_id" | "is_active">>;

export function useSaveOrgItem(kind: OrgKind) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, input }: { id?: string; input: OrgInput }) =>
      id
        ? (await api.patch<ApiSuccess<OrgItem>>(`/${kind}/${id}`, input)).data.data
        : (await api.post<ApiSuccess<OrgItem>>(`/${kind}`, input)).data.data,
    onSuccess: () => client.invalidateQueries({ queryKey: [kind] }),
  });
}
