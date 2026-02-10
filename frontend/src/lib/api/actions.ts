import { apiFetch } from "@/lib/api";
import type { Action, ActionListItem } from "@/types";

export async function listActions(): Promise<ActionListItem[]> {
  return apiFetch<ActionListItem[]>("/actions");
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
