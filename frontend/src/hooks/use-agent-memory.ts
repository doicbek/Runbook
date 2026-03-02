import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAgentMemory, updateAgentMemory } from "@/lib/api/agent-memory";

export function useAgentMemory(agentType: string) {
  return useQuery({
    queryKey: ["agent-memory", agentType],
    queryFn: () => getAgentMemory(agentType),
    enabled: !!agentType,
    retry: false,
  });
}

export function useUpdateAgentMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentType, content }: { agentType: string; content: string }) =>
      updateAgentMemory(agentType, content),
    onSuccess: (_, { agentType }) => {
      qc.invalidateQueries({ queryKey: ["agent-memory", agentType] });
    },
  });
}
