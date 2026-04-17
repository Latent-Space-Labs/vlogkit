import type { StoryboardSection, StoryboardSegment } from "@/lib/api";
import { SegmentBlock } from "./segment-block";

export function SectionRow({
  section,
  selectedSegmentKey,
  onSelectSegment,
}: {
  section: StoryboardSection;
  selectedSegmentKey: string | null;
  onSelectSegment: (key: string, segment: StoryboardSegment) => void;
}) {
  return (
    <section className="border-t border-[var(--color-border-whisper)] pt-4 mt-4 first:border-t-0 first:mt-0 first:pt-0">
      <h3 className="mb-3">{section.title}</h3>
      {section.notes ? (
        <p className="text-sm text-[var(--color-muted)] mb-2">{section.notes}</p>
      ) : null}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {(section.segments ?? []).map((seg, idx) => {
          const key = `${section.title}/${idx}`;
          return (
            <SegmentBlock
              key={key}
              segment={seg}
              selected={selectedSegmentKey === key}
              onSelect={() => onSelectSegment(key, seg)}
            />
          );
        })}
      </div>
    </section>
  );
}
