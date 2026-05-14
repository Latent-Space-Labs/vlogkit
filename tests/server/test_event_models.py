"""Tests for new score and agent-stage event models."""

from __future__ import annotations

import pytest


def test_score_started_event_serializes_with_type_discriminator():
    from vlogkit.server.schemas import ScoreStarted

    evt = ScoreStarted(job_id="abc", total_scenes=24)
    dumped = evt.model_dump()
    assert dumped["type"] == "score.started"
    assert dumped["job_id"] == "abc"
    assert dumped["total_scenes"] == 24


def test_score_progress_event_fields():
    from vlogkit.server.schemas import ScoreProgress

    evt = ScoreProgress(
        job_id="abc", scored=3, total_scenes=10,
        current_clip="clip.mp4", current_scene_index=2,
    )
    dumped = evt.model_dump()
    assert dumped["type"] == "score.progress"
    assert dumped["scored"] == 3
    assert dumped["current_clip"] == "clip.mp4"


def test_score_clip_done_event_fields():
    from vlogkit.server.schemas import ScoreClipDone

    evt = ScoreClipDone(job_id="abc", clip_filename="clip.mp4", average_composite=78.5)
    dumped = evt.model_dump()
    assert dumped["type"] == "score.clip_done"
    assert dumped["average_composite"] == 78.5


def test_score_complete_event_fields():
    from vlogkit.server.schemas import ScoreComplete

    evt = ScoreComplete(job_id="abc", total_scored=24)
    assert evt.model_dump()["type"] == "score.complete"


def test_score_failed_event_fields():
    from vlogkit.server.schemas import ScoreFailed

    evt = ScoreFailed(job_id="abc", error="boom")
    assert evt.model_dump()["type"] == "score.failed"
    assert evt.model_dump()["error"] == "boom"


def test_storyboard_agent_started_event_fields():
    from vlogkit.server.schemas import StoryboardAgentStarted

    evt = StoryboardAgentStarted(job_id="abc", stage="director")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_started"
    assert dumped["stage"] == "director"


def test_storyboard_agent_complete_event_fields():
    from vlogkit.server.schemas import StoryboardAgentComplete

    evt = StoryboardAgentComplete(job_id="abc", stage="editor", summary="Picked 12 segments")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_complete"
    assert dumped["stage"] == "editor"
    assert dumped["summary"] == "Picked 12 segments"


def test_storyboard_agent_failed_event_fields():
    from vlogkit.server.schemas import StoryboardAgentFailed

    evt = StoryboardAgentFailed(job_id="abc", stage="polisher", reason="schema validation failed")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_failed"
    assert dumped["reason"] == "schema validation failed"


def test_storyboard_agent_started_rejects_invalid_stage():
    import pytest
    from pydantic import ValidationError

    from vlogkit.server.schemas import StoryboardAgentStarted

    with pytest.raises(ValidationError):
        StoryboardAgentStarted(job_id="abc", stage="invalid")  # type: ignore[arg-type]
