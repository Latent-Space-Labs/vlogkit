"""Unit tests for the storyboard agents (Director / Editor / Polisher)."""

from __future__ import annotations

import pytest

from vlogkit.storyboard.agents.base import AgentError, parse_json_response


def test_agent_error_records_stage_and_reason():
    err = AgentError(stage="director", reason="missing field")
    assert err.stage == "director"
    assert err.reason == "missing field"
    assert "director" in str(err)
    assert "missing field" in str(err)


def test_parse_json_response_plain_json():
    raw = '{"title": "Test", "sections": []}'
    assert parse_json_response(raw) == {"title": "Test", "sections": []}


def test_parse_json_response_strips_json_fence():
    raw = '```json\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_strips_unlabeled_fence():
    raw = '```\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_raises_value_error_on_garbage():
    with pytest.raises(ValueError):
        parse_json_response("this is not json")


def test_director_run_parses_valid_response():
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, run

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"title": "Hot Open", "sections": [{"id": "s1", "title": "Open", "goal": "tease", "target_duration": 8, "scene_types": ["hook"]}], "arc_rationale": "starts strong"}'

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(start=0, end=5, murch=MurchScore(
                scene_type="hook", aesthetic=80, credibility=80, impact=80,
                memorability=80, fun=80, composite=80,
            )),
            SceneSegment(start=5, end=10, murch=MurchScore(
                scene_type="narrative", aesthetic=50, credibility=50, impact=50,
                memorability=50, fun=50, composite=50,
            )),
        ],
        summary="a fun morning",
        file_hash="x",
    )

    plan = run(
        analyses=[analysis],
        strategy="energy-arc",
        context="a recent trip",
        backend=FakeBackend(),
    )
    assert isinstance(plan, DirectorPlan)
    assert plan.title == "Hot Open"
    assert len(plan.sections) == 1
    assert plan.sections[0].id == "s1"
    assert plan.sections[0].scene_types == ["hook"]

    # Verify the prompt mentions the strategy hint and scene-type counts
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "energy-arc" in prompt or "energy arc" in prompt.lower()
    assert "hook" in prompt and "narrative" in prompt


def test_director_run_handles_scenes_without_murch():
    """When scenes lack MurchScore, scene-type counts default to 'unknown'."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, SceneSegment
    from vlogkit.storyboard.agents.director import run

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"title": "T", "sections": [], "arc_rationale": "r"}'

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )

    run(analyses=[analysis], strategy="chronological", context="trip", backend=FakeBackend())

    assert "unknown" in captured_prompts[0]


def test_director_run_raises_agent_error_on_malformed_json():
    from vlogkit.models import ClipAnalysis, ClipMetadata
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return "this is not json"

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    with pytest.raises(AgentError) as exc:
        run(analyses=[analysis], strategy="energy-arc", context="trip", backend=FakeBackend())
    assert exc.value.stage == "director"


def test_director_run_raises_agent_error_on_missing_fields():
    from vlogkit.models import ClipAnalysis, ClipMetadata
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return '{"sections": []}'  # missing required title

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    with pytest.raises(AgentError):
        run(analyses=[analysis], strategy="energy-arc", context="trip", backend=FakeBackend())


def test_editor_run_parses_valid_response():
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import EditorAssignments, run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return '{"assignments": [{"section_id": "s1", "picks": [{"clip_path": "clip.mp4", "scene_index": 0, "in_point": 0.0, "out_point": 5.0, "reason": "best hook"}]}]}'

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="Open", goal="tease", target_duration=5, scene_types=["hook"])],
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5, murch=MurchScore(
            scene_type="hook", aesthetic=80, credibility=80, impact=80,
            memorability=80, fun=80, composite=80,
        ))],
        file_hash="x",
    )

    assignments = run(plan=plan, analyses=[analysis], backend=FakeBackend())
    assert isinstance(assignments, EditorAssignments)
    assert len(assignments.assignments) == 1
    assert assignments.assignments[0].section_id == "s1"
    assert assignments.assignments[0].picks[0].clip_path == "clip.mp4"
    assert assignments.assignments[0].picks[0].in_point == 0.0
    assert assignments.assignments[0].picks[0].out_point == 5.0


def test_editor_run_clamps_in_out_points_to_scene_bounds():
    """If the LLM picks in/out points outside the scene's range, the orchestrator clamps them."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            # LLM picks in_point=99 (beyond scene end of 5) and out_point=100
            return '{"assignments": [{"section_id": "s1", "picks": [{"clip_path": "clip.mp4", "scene_index": 0, "in_point": 99.0, "out_point": 100.0, "reason": "out of bounds"}]}]}'

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="Open", goal="tease", target_duration=5, scene_types=["hook"])],
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5)],
        file_hash="x",
    )

    assignments = run(plan=plan, analyses=[analysis], backend=FakeBackend())
    pick = assignments.assignments[0].picks[0]
    # Both points clamped to the scene's [0, 5] range
    assert 0 <= pick.in_point <= 5
    assert 0 <= pick.out_point <= 5
    assert pick.in_point <= pick.out_point


def test_editor_run_raises_agent_error_on_malformed_json():
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return "garbage"

    with pytest.raises(AgentError) as exc:
        run(plan=DirectorPlan(title="T"), analyses=[], backend=FakeBackend())
    assert exc.value.stage == "editor"
