import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTask, getTaskLogs, runTaskCode, updateTask } from "@/lib/api/tasks";

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      actionId,
      ...body
    }: {
      actionId: string;
      prompt: string;
      agent_type?: string;
      dependencies?: string[];
    }) => createTask(actionId, body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["action", data.action_id] });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      actionId,
      taskId,
      ...body
    }: {
      actionId: string;
      taskId: string;
      prompt?: string;
      dependencies?: string[];
    }) => updateTask(actionId, taskId, body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["action", data.action_id] });
    },
  });
}

export function useTaskLogs(actionId: string, taskId: string, enabled = true) {
  return useQuery({
    queryKey: ["task-logs", actionId, taskId],
    queryFn: () => getTaskLogs(actionId, taskId),
    enabled: enabled && !!actionId && !!taskId,
  });
}

export function useRunCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      actionId,
      taskId,
      code,
    }: {
      actionId: string;
      taskId: string;
      code?: string;
    }) => runTaskCode(actionId, taskId, code),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["action", variables.actionId],
      });
    },
  });
}
