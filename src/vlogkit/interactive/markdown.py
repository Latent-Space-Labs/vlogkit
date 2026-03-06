"""Storyboard <-> editable Markdown conversion."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Storyboard, StoryboardSection, StoryboardSegment


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def storyboard_to_markdown(storyboard: Storyboard) -> str:
    lines: list[str] = []
    lines.append(f"# {storyboard.title}")
    lines.append("")

    if storyboard.llm_rationale:
        lines.append(f"<!-- Rationale: {storyboard.llm_rationale} -->")
        lines.append("")

    for section in storyboard.sections:
        lines.append(f"## {section.title}")
        if section.notes:
            lines.append(f"<!-- {section.notes} -->")
        lines.append("")

        for seg in section.segments:
            check = "x" if seg.include else " "
            in_t = _format_time(seg.in_point)
            out_t = _format_time(seg.out_point)
            label = seg.label or seg.clip_path.name
            lines.append(f"- [{check}] {seg.clip_path.name} [{in_t} - {out_t}] \"{label}\"")

        lines.append("")

    included = storyboard.included_duration()
    lines.append(f"<!-- Total included duration: {_format_time(included)} -->")
    return "\n".join(lines)


_SEGMENT_RE = re.compile(
    r"^- \[(?P<check>[xX ])\] "
    r"(?P<filename>\S+) "
    r"\[(?P<in_time>\d+:\d{2}) - (?P<out_time>\d+:\d{2})\] "
    r"\"(?P<label>[^\"]*)\""
)


def _parse_time(t: str) -> float:
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def markdown_to_storyboard(text: str, project_root: Path | None = None) -> Storyboard:
    lines = text.strip().split("\n")

    title = "Untitled Vlog"
    sections: list[StoryboardSection] = []
    current_section: StoryboardSection | None = None
    rationale = ""

    for line in lines:
        stripped = line.strip()

        # Title
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            continue

        # Rationale comment
        if stripped.startswith("<!-- Rationale:"):
            rationale = stripped.replace("<!-- Rationale:", "").replace("-->", "").strip()
            continue

        # Section header
        if stripped.startswith("## "):
            if current_section:
                sections.append(current_section)
            section_title = stripped[3:].strip()
            current_section = StoryboardSection(title=section_title)
            continue

        # Section notes (comment right after section header)
        if stripped.startswith("<!--") and stripped.endswith("-->") and current_section is not None:
            note = stripped[4:-3].strip()
            if not note.startswith("Total included"):
                current_section.notes = note
            continue

        # Segment line
        m = _SEGMENT_RE.match(stripped)
        if m and current_section is not None:
            filename = m.group("filename")
            clip_path = Path(filename)
            if project_root:
                full = project_root / filename
                if full.exists():
                    clip_path = full
                else:
                    matches = list(project_root.rglob(filename))
                    if matches:
                        clip_path = matches[0]

            current_section.segments.append(StoryboardSegment(
                clip_path=clip_path,
                in_point=_parse_time(m.group("in_time")),
                out_point=_parse_time(m.group("out_time")),
                label=m.group("label"),
                include=m.group("check").lower() == "x",
            ))

    if current_section:
        sections.append(current_section)

    total = 0.0
    for sec in sections:
        for seg in sec.segments:
            if seg.include:
                total += seg.out_point - seg.in_point

    return Storyboard(
        title=title,
        sections=sections,
        total_duration=total,
        llm_rationale=rationale,
    )
