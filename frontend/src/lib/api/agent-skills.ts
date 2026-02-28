import { apiFetch } from "@/lib/api";
import type { AgentSkill } from "@/types";

export async function listSkills(agentType?: string): Promise<AgentSkill[]> {
  const params = agentType ? `?agent_type=${encodeURIComponent(agentType)}` : "";
  return apiFetch<AgentSkill[]>(`/skills${params}`);
}

export async function createSkill(body: {
  agent_type: string;
  title: string;
  description: string;
  category?: string;
  priority?: string;
}): Promise<AgentSkill> {
  return apiFetch<AgentSkill>("/skills", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateSkill(
  id: string,
  body: { title?: string; description?: string; is_active?: boolean; priority?: string; status?: string; category?: string }
): Promise<AgentSkill> {
  return apiFetch<AgentSkill>(`/skills/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteSkill(id: string): Promise<void> {
  return apiFetch<void>(`/skills/${id}`, { method: "DELETE" });
}

export interface SkillStats {
  total: number;
  by_category: Record<string, number>;
  by_priority: Record<string, number>;
  by_source: Record<string, number>;
  promoted: number;
  pending_high_priority: number;
}

export async function getSkillStats(): Promise<SkillStats> {
  return apiFetch<SkillStats>("/skills/stats");
}
