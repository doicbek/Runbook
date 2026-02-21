import { apiFetch } from "@/lib/api";
import type { ModelsResponse } from "@/types";

export async function getAvailableModels(): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>("/models");
}
