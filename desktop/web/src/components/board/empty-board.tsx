import { api } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function EmptyBoard({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => api.regenerateStoryboard(projectId),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <div className="text-center py-24 px-8">
      <h2 className="text-2xl font-bold mb-3">No storyboard yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto mb-6">
        Once your clips are analyzed, generate a storyboard and arrange the
        sequence the way you want.
      </p>
      <button
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        {mut.isPending ? "Generating…" : "Generate storyboard"}
      </button>
    </div>
  );
}
