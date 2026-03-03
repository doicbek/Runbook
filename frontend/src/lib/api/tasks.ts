import { apiFetch, API_BASE } from "@/lib/api";
import type { AgentIteration, Artifact, ArtifactDiffResponse, ArtifactVersion, CodeExecutionResult, LogEntry, Task } from "@/types";

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
  body: { prompt?: string; model?: string | null; agent_type?: string; dependencies?: string[]; timeout_seconds?: number | null }
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

export async function getTaskIterations(
  actionId: string,
  taskId: string
): Promise<AgentIteration[]> {
  return apiFetch<AgentIteration[]>(
    `/actions/${actionId}/tasks/${taskId}/iterations`
  );
}

export async function pauseTask(
  actionId: string,
  taskId: string
): Promise<void> {
  await apiFetch(`/actions/${actionId}/tasks/${taskId}/pause`, {
    method: "POST",
  });
}

export async function resumeTask(
  actionId: string,
  taskId: string,
  body?: { guidance?: string; redirect?: boolean }
): Promise<void> {
  await apiFetch(`/actions/${actionId}/tasks/${taskId}/resume`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

export function getArtifactUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${artifactId}/content`;
}

export async function getArtifact(artifactId: string): Promise<Artifact> {
  return apiFetch<Artifact>(`/artifacts/${artifactId}`);
}

export async function listArtifactVersions(artifactId: string): Promise<ArtifactVersion[]> {
  return apiFetch<ArtifactVersion[]>(`/artifacts/${artifactId}/versions`);
}

export function getArtifactVersionContentUrl(artifactId: string, version: number): string {
  return `${API_BASE}/artifacts/${artifactId}/versions/${version}/content`;
}

export async function getArtifactDiff(artifactId: string, v1: number, v2: number): Promise<ArtifactDiffResponse> {
  return apiFetch<ArtifactDiffResponse>(`/artifacts/${artifactId}/diff?v1=${v1}&v2=${v2}`);
}
