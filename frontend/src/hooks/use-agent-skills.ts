import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  listConcepts,
  createConcept,
  deleteConcept,
  listRelations,
  createRelation,
  deleteRelation,
  getOntologyGraph,
} from "@/lib/api/agent-skills";

export function useSkills(agentType?: string) {
  return useQuery({
    queryKey: ["skills", agentType ?? "all"],
    queryFn: () => listSkills(agentType),
  });
}

export function useCreateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createSkill,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUpdateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      title?: string;
      description?: string;
      is_active?: boolean;
      priority?: string;
      status?: string;
      category?: string;
    }) => updateSkill(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteSkill,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      queryClient.invalidateQueries({ queryKey: ["ontology"] });
    },
  });
}

// ── Ontology hooks ──────────────────────────────────────────────────────

export function useConcepts(conceptType?: string) {
  return useQuery({
    queryKey: ["ontology", "concepts", conceptType ?? "all"],
    queryFn: () => listConcepts(conceptType),
  });
}

export function useCreateConcept() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createConcept,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ontology"] });
    },
  });
}

export function useDeleteConcept() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConcept,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ontology"] });
    },
  });
}

export function useRelations(nodeId?: string) {
  return useQuery({
    queryKey: ["ontology", "relations", nodeId ?? "all"],
    queryFn: () => listRelations(nodeId),
  });
}

export function useCreateRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createRelation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ontology"] });
    },
  });
}

export function useDeleteRelation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteRelation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ontology"] });
    },
  });
}

export function useOntologyGraph(agentType?: string) {
  return useQuery({
    queryKey: ["ontology", "graph", agentType ?? "all"],
    queryFn: () => getOntologyGraph(agentType),
  });
}
