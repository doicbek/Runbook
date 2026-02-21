import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getApiStatus,
  getPlannerConfig,
  modifySystemPrompt,
  previewPlan,
  updatePlannerConfig,
} from "@/lib/api/planner-config";
import type { PlannerConfig } from "@/types";

export function usePlannerConfig() {
  return useQuery({
    queryKey: ["planner-config"],
    queryFn: getPlannerConfig,
  });
}

export function useApiStatus() {
  return useQuery({
    queryKey: ["api-status"],
    queryFn: getApiStatus,
    staleTime: 60_000,
  });
}

export function useUpdatePlannerConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<PlannerConfig>) => updatePlannerConfig(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planner-config"] }),
  });
}

export function usePreviewPlan() {
  return useMutation({
    mutationFn: ({ prompt, systemPrompt }: { prompt: string; systemPrompt?: string }) =>
      previewPlan(prompt, systemPrompt),
  });
}

export function useModifySystemPrompt() {
  return useMutation({
    mutationFn: (body: { instruction: string; current_prompt?: string; model?: string }) =>
      modifySystemPrompt(body),
  });
}
