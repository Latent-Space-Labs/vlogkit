import { SortableContext, horizontalListSortingStrategy } from "@dnd-kit/sortable";
import type { StoryboardSection, StoryboardSegment } from "@/lib/api";
import { SegmentBlock } from "./segment-block";

export function SectionRow({
  sectionIndex,
  section,
  selectedSegmentKey,
  onSelectSegment,
}: {
  sectionIndex: number;
  section: StoryboardSection;
  selectedSegmentKey: string | null;
  onSelectSegment: (key: string, segment: StoryboardSegment) => void;
}) {
  const segments = section.segments ?? [];
  const items = segments.map((_, idx) => `${sectionIndex}:${idx}`);
  return (
    <section className="border-t border-[var(--color-border-whisper)] pt-4 mt-4 first:border-t-0 first:mt-0 first:pt-0">
      <h3 className="mb-3">{section.title}</h3>
      {section.notes ? (
        <p className="text-sm text-[var(--color-muted)] mb-2">{section.notes}</p>
      ) : null}
      <SortableContext items={items} strategy={horizontalListSortingStrategy}>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {segments.map((seg, idx) => {
            const id = `${sectionIndex}:${idx}`;
            return (
              <SegmentBlock
                key={id}
                id={id}
                segment={seg}
                selected={selectedSegmentKey === id}
                onSelect={() => onSelectSegment(id, seg)}
              />
            );
          })}
        </div>
      </SortableContext>
    </section>
  );
}
