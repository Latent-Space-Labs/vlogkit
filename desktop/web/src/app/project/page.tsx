"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { ClipsTab } from "@/components/clips/clip-list";

function ProjectInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const tab = params.get("tab") ?? "clips";

  if (!id) {
    return (
      <main className="max-w-3xl mx-auto px-8 py-16">
        <p className="text-[var(--color-muted)]">No project id.</p>
      </main>
    );
  }

  return (
    <main className="max-w-5xl mx-auto px-8 py-10">
      <header className="mb-6">
        <button
          onClick={() => router.push("/")}
          className="text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
        >
          ← All projects
        </button>
        <div className="mt-2 flex items-center gap-4">
          <h2 className="text-2xl font-bold">Project</h2>
          <nav className="flex gap-1">
            {(["clips", "board", "search"] as const).map((t) => (
              <button
                key={t}
                onClick={() => router.push(`/project?id=${id}&tab=${t}`)}
                className={
                  "px-3 py-1 rounded-[4px] text-sm " +
                  (t === tab
                    ? "bg-[var(--color-accent)] text-white"
                    : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]")
                }
              >
                {t}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {tab === "clips" && <ClipsTab projectId={id} />}
      {tab === "board" && <Placeholder name="Storyboard editor — Plan 4" />}
      {tab === "search" && <Placeholder name="Semantic search — Plan 5" />}
    </main>
  );
}

function Placeholder({ name }: { name: string }) {
  return (
    <p className="text-[var(--color-muted)] py-16 text-center">{name}</p>
  );
}

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectInner />
    </Suspense>
  );
}
