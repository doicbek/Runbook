import { apiFetch } from "@/lib/api";
import type { ActionSchedule, ActionScheduleDetail } from "@/types";

export async function listSchedules(): Promise<ActionSchedule[]> {
  return apiFetch<ActionSchedule[]>("/schedules");
}

export async function getSchedule(id: string): Promise<ActionScheduleDetail> {
  return apiFetch<ActionScheduleDetail>(`/schedules/${id}`);
}

export async function createSchedule(body: {
  title: string;
  root_prompt: string;
  cron_expression: string;
  is_active?: boolean;
  template_id?: string;
}): Promise<ActionSchedule> {
  return apiFetch<ActionSchedule>("/schedules", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateSchedule(
  id: string,
  body: {
    title?: string;
    root_prompt?: string;
    cron_expression?: string;
    is_active?: boolean;
  }
): Promise<ActionSchedule> {
  return apiFetch<ActionSchedule>(`/schedules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteSchedule(id: string): Promise<void> {
  return apiFetch<void>(`/schedules/${id}`, { method: "DELETE" });
}

export async function runScheduleNow(id: string): Promise<ActionSchedule> {
  return apiFetch<ActionSchedule>(`/schedules/${id}/run-now`, {
    method: "POST",
  });
}
