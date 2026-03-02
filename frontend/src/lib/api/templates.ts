import { apiFetch } from "@/lib/api";
import type { Action, ActionTemplate } from "@/types";

export async function listTemplates(params?: {
  search?: string;
  tag?: string;
}): Promise<ActionTemplate[]> {
  const searchParams = new URLSearchParams();
  if (params?.search) searchParams.set("search", params.search);
  if (params?.tag) searchParams.set("tag", params.tag);
  const qs = searchParams.toString();
  return apiFetch<ActionTemplate[]>(`/templates${qs ? `?${qs}` : ""}`);
}

export async function getTemplate(id: string): Promise<ActionTemplate> {
  return apiFetch<ActionTemplate>(`/templates/${id}`);
}

export async function createTemplate(body: {
  title: string;
  description?: string;
  root_prompt: string;
  tags?: string[];
}): Promise<ActionTemplate> {
  return apiFetch<ActionTemplate>("/templates", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTemplate(
  id: string,
  body: { title?: string; description?: string; tags?: string[] }
): Promise<ActionTemplate> {
  return apiFetch<ActionTemplate>(`/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteTemplate(id: string): Promise<void> {
  return apiFetch<void>(`/templates/${id}`, { method: "DELETE" });
}

export async function useTemplateApi(id: string): Promise<Action> {
  return apiFetch<Action>(`/templates/${id}/use`, { method: "POST" });
}

export async function saveAsTemplate(actionId: string): Promise<ActionTemplate> {
  return apiFetch<ActionTemplate>(`/templates/from-action/${actionId}`, {
    method: "POST",
  });
}
