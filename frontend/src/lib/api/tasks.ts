import { apiFetch, API_BASE } from "@/lib/api";
import type { CodeExecutionResult, LogEntry, Task } from "@/types";

export async function createTask(
  actionId: string,
  body: { prompt: string; agent_type?: string; dependencies?: string[] }
): Promise<Task> {
  return apiFetch<Task>(`/actions/${actionId}/tasks`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateTask(
  actionId: string,
  taskId: string,
  body: { prompt?: string; model?: string | null; agent_type?: string; dependencies?: string[] }
): Promise<Task> {
  return apiFetch<Task>(`/actions/${actionId}/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function getTaskLogs(
  actionId: string,
  taskId: string
): Promise<LogEntry[]> {
  return apiFetch<LogEntry[]>(`/actions/${actionId}/tasks/${taskId}/logs`);
}

export async function runTaskCode(
  actionId: string,
  taskId: string,
  code?: string
): Promise<CodeExecutionResult> {
  return apiFetch<CodeExecutionResult>(
    `/actions/${actionId}/tasks/${taskId}/run-code`,
    {
      method: "POST",
      body: JSON.stringify(code ? { code } : {}),
    }
  );
}

export function getArtifactUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${artifactId}/content`;
}
