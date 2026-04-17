import { ProjectList } from "@/components/projects/project-list";
import { OpenFolderButton } from "@/components/projects/open-folder-button";

export default function HomePage() {
  return (
    <main className="max-w-3xl mx-auto px-8 py-16">
      <header className="flex items-end justify-between mb-10">
        <div>
          <h1>vlogkit</h1>
          <p className="text-[var(--color-muted)] mt-2 text-lg">
            Turn a folder of clips into an edited story.
          </p>
        </div>
        <OpenFolderButton />
      </header>
      <section className="bg-[var(--color-background-alt)] rounded-[16px] p-6">
        <ProjectList />
      </section>
    </main>
  );
}
