import { apiFetch } from "@/lib/api";
import type { AgentSkill, SkillConcept, SkillRelation, OntologyGraph } from "@/types";

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

// ── Ontology: Concepts ──────────────────────────────────────────────────

export async function listConcepts(conceptType?: string): Promise<SkillConcept[]> {
  const params = conceptType ? `?concept_type=${encodeURIComponent(conceptType)}` : "";
  return apiFetch<SkillConcept[]>(`/skills/ontology/concepts${params}`);
}

export async function createConcept(body: {
  name: string;
  concept_type: string;
  description?: string;
}): Promise<SkillConcept> {
  return apiFetch<SkillConcept>("/skills/ontology/concepts", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteConcept(id: string): Promise<void> {
  return apiFetch<void>(`/skills/ontology/concepts/${id}`, { method: "DELETE" });
}

// ── Ontology: Relations ─────────────────────────────────────────────────

export async function listRelations(nodeId?: string): Promise<SkillRelation[]> {
  const params = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
  return apiFetch<SkillRelation[]>(`/skills/ontology/relations${params}`);
}

export async function createRelation(body: {
  from_id: string;
  relation_type: string;
  to_id: string;
  properties?: Record<string, unknown>;
}): Promise<SkillRelation> {
  return apiFetch<SkillRelation>("/skills/ontology/relations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteRelation(id: string): Promise<void> {
  return apiFetch<void>(`/skills/ontology/relations/${id}`, { method: "DELETE" });
}

// ── Ontology: Graph ─────────────────────────────────────────────────────

export async function getOntologyGraph(agentType?: string): Promise<OntologyGraph> {
  const params = agentType ? `?agent_type=${encodeURIComponent(agentType)}` : "";
  return apiFetch<OntologyGraph>(`/skills/ontology/graph${params}`);
}
