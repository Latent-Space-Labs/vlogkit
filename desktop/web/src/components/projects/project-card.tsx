import type { Project } from "@/lib/api";

export function ProjectCard({
  project,
  onOpen,
  onForget,
}: {
  project: Project;
  onOpen: (id: string) => void;
  onForget: (id: string) => void;
}) {
  const lastOpenedDate = new Date(project.last_opened * 1000);
  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-5 flex items-center justify-between transition hover:-translate-y-[1px]"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <button
        onClick={() => onOpen(project.id)}
        className="flex-1 text-left"
      >
        <div className="font-semibold text-lg">{project.name}</div>
        <div className="text-sm text-[var(--color-muted)] truncate">
          {project.path}
        </div>
        <div className="text-xs text-[var(--color-placeholder)] mt-1">
          Last opened {lastOpenedDate.toLocaleString()}
        </div>
      </button>
      <button
        onClick={() => onForget(project.id)}
        className="ml-4 text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
      >
        Forget
      </button>
    </div>
  );
}
