"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function OpenFolderButton() {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      // Prefer native dialog via preload if available; fall back to prompt.
      const win = window as typeof window & {
        vlogkitOpenFolder?: () => Promise<string | null>;
      };
      const path = win.vlogkitOpenFolder
        ? await win.vlogkitOpenFolder()
        : prompt("Folder path:");
      if (!path) return null;
      return api.registerProject(path);
    },
    onSuccess: (project) => {
      if (project) qc.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 transition"
    >
      {mutation.isPending ? "Opening…" : "Open folder"}
    </button>
  );
}
