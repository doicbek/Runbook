import { useQuery } from "@tanstack/react-query";
import { getTaskIterations } from "@/lib/api/tasks";

export function useTaskIterations(
  actionId: string,
  taskId: string,
  opts?: { enabled?: boolean; refetchInterval?: number | false }
) {
  return useQuery({
    queryKey: ["task-iterations", actionId, taskId],
    queryFn: () => getTaskIterations(actionId, taskId),
    enabled: (opts?.enabled ?? true) && !!actionId && !!taskId,
    refetchInterval: opts?.refetchInterval,
  });
}
