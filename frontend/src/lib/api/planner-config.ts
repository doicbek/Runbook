import { apiFetch } from "@/lib/api";
import type {
  ApiKeyStatus,
  PlannerConfig,
  PlannerPreviewResponse,
} from "@/types";

export async function getPlannerConfig(): Promise<PlannerConfig> {
  return apiFetch<PlannerConfig>("/planner-config");
}

export async function updatePlannerConfig(
  body: Partial<PlannerConfig>
): Promise<PlannerConfig> {
  return apiFetch<PlannerConfig>("/planner-config", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function getApiStatus(): Promise<ApiKeyStatus[]> {
  return apiFetch<ApiKeyStatus[]>("/planner-config/api-status");
}

export async function previewPlan(
  prompt: string,
  systemPrompt?: string
): Promise<PlannerPreviewResponse> {
  return apiFetch<PlannerPreviewResponse>("/planner-config/preview", {
    method: "POST",
    body: JSON.stringify({ prompt, system_prompt: systemPrompt }),
  });
}

export async function modifySystemPrompt(body: {
  instruction: string;
  current_prompt?: string;
  model?: string;
}): Promise<{ system_prompt: string }> {
  return apiFetch<{ system_prompt: string }>("/planner-config/modify-prompt", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
