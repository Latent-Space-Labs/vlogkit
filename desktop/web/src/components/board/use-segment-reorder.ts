import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Storyboard } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function useSegmentReorder(projectId: string) {
  const qc = useQueryClient();
  const key = [...queryKeys.project(projectId), "storyboard"];

  return useMutation({
    mutationFn: async (sb: Storyboard) => api.putStoryboard(projectId, sb),
    onMutate: async (newSb) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Storyboard>(key);
      qc.setQueryData(key, newSb);
      return { prev };
    },
    onError: (_err, _new, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
