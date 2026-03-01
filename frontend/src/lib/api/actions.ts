import { apiFetch } from "@/lib/api";
import type { Action, PaginatedActions } from "@/types";

export async function listActions(params?: {
  search?: string;
  cursor?: string;
  status?: string;
  limit?: number;
}): Promise<PaginatedActions> {
  const searchParams = new URLSearchParams();
  if (params?.search) searchParams.set("search", params.search);
  if (params?.cursor) searchParams.set("cursor", params.cursor);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return apiFetch<PaginatedActions>(`/actions${qs ? `?${qs}` : ""}`);
}

export async function getAction(id: string): Promise<Action> {
  return apiFetch<Action>(`/actions/${id}`);
}

export async function createAction(body: {
  root_prompt: string;
  title?: string;
}): Promise<Action> {
  return apiFetch<Action>("/actions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateAction(
  id: string,
  body: { title?: string; root_prompt?: string }
): Promise<Action> {
  return apiFetch<Action>(`/actions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function runAction(id: string): Promise<Action> {
  return apiFetch<Action>(`/actions/${id}/run`, {
    method: "POST",
  });
}

export async function deleteAction(id: string): Promise<void> {
  await apiFetch<void>(`/actions/${id}`, {
    method: "DELETE",
  });
}

export interface BreadcrumbItem {
  id: string;
  title: string;
  depth: number;
}

export async function getBreadcrumbs(id: string): Promise<BreadcrumbItem[]> {
  return apiFetch<BreadcrumbItem[]>(`/actions/${id}/breadcrumbs`);
}
