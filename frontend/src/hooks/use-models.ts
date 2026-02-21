import { useQuery } from "@tanstack/react-query";
import { getAvailableModels } from "@/lib/api/models";

export function useAvailableModels() {
  return useQuery({
    queryKey: ["available-models"],
    queryFn: getAvailableModels,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
