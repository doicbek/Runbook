import { apiFetch } from "@/lib/api";
import type {
  AgentDefinition,
  ModifyRequest,
  ModifyResponse,
  ScaffoldRequest,
  ScaffoldResponse,
  ToolCatalogEntry,
} from "@/types";

export async function listAgentDefinitions(): Promise<AgentDefinition[]> {
  return apiFetch<AgentDefinition[]>("/agent-definitions");
}

export async function getAgentDefinition(id: string): Promise<AgentDefinition> {
  return apiFetch<AgentDefinition>(`/agent-definitions/${id}`);
}

export async function createAgentDefinition(
  body: Partial<AgentDefinition>
): Promise<AgentDefinition> {
  return apiFetch<AgentDefinition>("/agent-definitions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateAgentDefinition(
  id: string,
  body: Partial<AgentDefinition>
): Promise<AgentDefinition> {
  return apiFetch<AgentDefinition>(`/agent-definitions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteAgentDefinition(id: string): Promise<void> {
  return apiFetch<void>(`/agent-definitions/${id}`, { method: "DELETE" });
}

export async function scaffoldAgentCode(
  body: ScaffoldRequest
): Promise<ScaffoldResponse> {
  return apiFetch<ScaffoldResponse>("/agent-definitions/scaffold", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listToolCatalog(): Promise<ToolCatalogEntry[]> {
  return apiFetch<ToolCatalogEntry[]>("/agent-definitions/tools");
}

export async function modifyAgentCode(
  id: string,
  body: ModifyRequest
): Promise<ModifyResponse> {
  return apiFetch<ModifyResponse>(`/agent-definitions/${id}/modify`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
