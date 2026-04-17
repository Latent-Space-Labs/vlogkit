export function EmptyState() {
  return (
    <div className="text-center py-24 px-8">
      <h2 className="text-2xl font-bold mb-3">No projects yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto">
        Drop a folder of video clips to get started. vlogkit will scan,
        analyze, and turn them into a storyboard you can edit.
      </p>
    </div>
  );
}
