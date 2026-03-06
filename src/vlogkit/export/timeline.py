"""Convert Storyboard to OpenTimelineIO Timeline."""

from __future__ import annotations

import opentimelineio as otio

from ..models import Storyboard


def storyboard_to_timeline(storyboard: Storyboard, fps: float = 30.0) -> otio.schema.Timeline:
    timeline = otio.schema.Timeline(name=storyboard.title)
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

    rate = otio.opentime.RationalTime(1, fps).rate

    for section in storyboard.sections:
        # Add a marker at section boundary
        for seg in section.segments:
            if not seg.include:
                continue

            clip_path = seg.clip_path.resolve()
            media_ref = otio.schema.ExternalReference(
                target_url=clip_path.as_uri(),
                available_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, rate),
                    duration=otio.opentime.RationalTime(
                        (seg.out_point - seg.in_point) * fps, rate
                    ),
                ),
            )

            source_range = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(seg.in_point * fps, rate),
                duration=otio.opentime.RationalTime(
                    (seg.out_point - seg.in_point) * fps, rate
                ),
            )

            clip = otio.schema.Clip(
                name=seg.label or seg.clip_path.name,
                media_reference=media_ref,
                source_range=source_range,
            )

            # Add transition if specified
            if seg.transition == "dissolve":
                transition = otio.schema.Transition(
                    transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                    in_offset=otio.opentime.RationalTime(fps * 0.5, rate),
                    out_offset=otio.opentime.RationalTime(fps * 0.5, rate),
                )
                track.append(transition)

            track.append(clip)

    timeline.tracks.append(track)
    return timeline
