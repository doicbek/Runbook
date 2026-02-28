import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listSkills,
  createSkill,
  updateSkill,
  deleteSkill,
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
    },
  });
}
