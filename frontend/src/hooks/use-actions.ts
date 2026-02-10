import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAction,
  getAction,
  listActions,
  runAction,
  updateAction,
} from "@/lib/api/actions";

export function useActions() {
  return useQuery({
    queryKey: ["actions"],
    queryFn: listActions,
  });
}

export function useAction(id: string) {
  return useQuery({
    queryKey: ["action", id],
    queryFn: () => getAction(id),
    enabled: !!id,
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

export function useRunAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runAction,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["action", data.id] });
    },
  });
}
