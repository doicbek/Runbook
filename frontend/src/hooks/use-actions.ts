import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAction,
  deleteAction,
  forkAction,
  getAction,
  getBreadcrumbs,
  listActions,
  listForks,
  runAction,
  updateAction,
} from "@/lib/api/actions";

export function useActions(params?: { search?: string; cursor?: string }) {
  return useQuery({
    queryKey: ["actions", params?.search, params?.cursor],
    queryFn: () => listActions(params),
  });
}

export function useAction(id: string, opts?: { refetchInterval?: number | false }) {
  return useQuery({
    queryKey: ["action", id],
    queryFn: () => getAction(id),
    enabled: !!id,
    refetchInterval: opts?.refetchInterval,
  });
}

export function useCreateAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createAction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["actions"] });
    },
  });
}

export function useUpdateAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; title?: string; root_prompt?: string }) =>
      updateAction(id, body),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["action", data.id] });
      queryClient.invalidateQueries({ queryKey: ["actions"] });
    },
  });
}

export function useBreadcrumbs(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["breadcrumbs", id],
    queryFn: () => getBreadcrumbs(id),
    enabled: enabled && !!id,
  });
}

export function useRunAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runAction,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["action", data.id] });
    },
  });
}

export function useDeleteAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteAction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["actions"] });
    },
  });
}

export function useForkAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: forkAction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["actions"] });
    },
  });
}

export function useForks(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["forks", id],
    queryFn: () => listForks(id),
    enabled: enabled && !!id,
  });
}
