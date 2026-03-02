import { useQuery } from "@tanstack/react-query";
import { getAgentToolAnalytics, getToolAnalytics } from "@/lib/api/tool-analytics";

export function useToolAnalytics(params?: { agent_type?: string; days?: number }) {
  return useQuery({
    queryKey: ["tool-analytics", params?.agent_type ?? "all", params?.days ?? "all"],
    queryFn: () => getToolAnalytics(params),
  });
}

export function useAgentToolAnalytics(agentType: string, days?: number) {
  return useQuery({
    queryKey: ["tool-analytics", "agent", agentType, days ?? "all"],
    queryFn: () => getAgentToolAnalytics(agentType, days),
    enabled: !!agentType,
  });
}
