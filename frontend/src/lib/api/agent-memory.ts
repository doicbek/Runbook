import { apiFetch } from "@/lib/api";

export interface AgentMemoryDetail {
  agent_type: string;
  content: string;
  version: number;
  updated_at: string;
  created_at: string;
}

export async function getAgentMemory(agentType: string): Promise<AgentMemoryDetail> {
  return apiFetch<AgentMemoryDetail>(`/agent-memory/${agentType}`);
}

export async function updateAgentMemory(
  agentType: string,
  content: string
): Promise<AgentMemoryDetail> {
  return apiFetch<AgentMemoryDetail>(`/agent-memory/${agentType}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}
