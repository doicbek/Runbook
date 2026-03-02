import { apiFetch } from "@/lib/api";

export interface ToolAnalyticsEntry {
  tool_name: string;
  total_calls: number;
  success_rate: number;
  avg_duration_ms: number;
  agent_types?: string[];
}

export async function getToolAnalytics(params?: {
  agent_type?: string;
  days?: number;
}): Promise<ToolAnalyticsEntry[]> {
  const search = new URLSearchParams();
  if (params?.agent_type) search.set("agent_type", params.agent_type);
  if (params?.days) search.set("days", String(params.days));
  const qs = search.toString();
  return apiFetch<ToolAnalyticsEntry[]>(`/analytics/tools${qs ? `?${qs}` : ""}`);
}

export async function getAgentToolAnalytics(
  agentType: string,
  days?: number,
): Promise<ToolAnalyticsEntry[]> {
  const qs = days ? `?days=${days}` : "";
  return apiFetch<ToolAnalyticsEntry[]>(`/analytics/agents/${agentType}/tools${qs}`);
}
