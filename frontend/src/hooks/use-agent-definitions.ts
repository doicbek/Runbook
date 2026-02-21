import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAgentDefinition,
  deleteAgentDefinition,
  getAgentDefinition,
  listAgentDefinitions,
  listToolCatalog,
  modifyAgentCode,
  scaffoldAgentCode,
  updateAgentDefinition,
} from "@/lib/api/agent-definitions";
import type { AgentDefinition, ModifyRequest, ScaffoldRequest } from "@/types";

export function useAgentDefinitions() {
  return useQuery({
    queryKey: ["agent-definitions"],
    queryFn: listAgentDefinitions,
  });
}

export function useAgentDefinition(id: string) {
  return useQuery({
    queryKey: ["agent-definitions", id],
    queryFn: () => getAgentDefinition(id),
    enabled: !!id,
  });
}

export function useToolCatalog() {
  return useQuery({
    queryKey: ["tool-catalog"],
    queryFn: listToolCatalog,
    staleTime: Infinity,
  });
}

export function useCreateAgentDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<AgentDefinition>) => createAgentDefinition(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-definitions"] });
    },
  });
}

export function useUpdateAgentDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<AgentDefinition> }) =>
      updateAgentDefinition(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["agent-definitions"] });
      qc.invalidateQueries({ queryKey: ["agent-definitions", id] });
    },
  });
}

export function useDeleteAgentDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAgentDefinition(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent-definitions"] });
    },
  });
}

export function useScaffoldAgent() {
  return useMutation({
    mutationFn: (body: ScaffoldRequest) => scaffoldAgentCode(body),
  });
}

export function useModifyAgent(id: string) {
  return useMutation({
    mutationFn: (body: ModifyRequest) => modifyAgentCode(id, body),
  });
}
