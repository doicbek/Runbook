import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTemplate,
  deleteTemplate,
  listTemplates,
  saveAsTemplate,
  updateTemplate,
  useTemplateApi,
} from "@/lib/api/templates";

export function useTemplates(params?: { search?: string; tag?: string }) {
  return useQuery({
    queryKey: ["templates", params?.search, params?.tag],
    queryFn: () => listTemplates(params),
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}

export function useUpdateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { title?: string; description?: string; tags?: string[] };
    }) => updateTemplate(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}

export function useUseTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => useTemplateApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["actions"] });
    },
  });
}

export function useSaveAsTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (actionId: string) => saveAsTemplate(actionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}
