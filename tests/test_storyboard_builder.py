"""Orchestration tests for the multi-agent storyboard pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_analysis(filename: str = "clip.mp4", path_str: str = "/tmp/clip.mp4"):
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment

    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=filename, path=Path(path_str), duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(start=0, end=5, murch=MurchScore(
                scene_type="hook", aesthetic=80, credibility=80, impact=80,
                memorability=80, fun=80, composite=80,
            )),
        ],
        file_hash="x",
    )


def test_build_storyboard_no_api_key_uses_chronological_fallback(tmp_path):
    from vlogkit.config import Settings
    from vlogkit.storyboard.builder import build_storyboard

    sb = build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key=""),
        strategy="energy-arc",
        context="trip",
    )
    # chronological_fallback labels the section "All Clips (Chronological)"
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_runs_all_three_agents(tmp_path, monkeypatch):
    """Happy path: Director → Editor → Polisher are called in order with the right data."""
    from vlogkit.config import Settings
    from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments

    call_order: list[str] = []

    def fake_director_run(**kwargs):
        call_order.append("director")
        return DirectorPlan(title="From Director", sections=[])

    def fake_editor_run(**kwargs):
        call_order.append("editor")
        assert kwargs["plan"].title == "From Director"
        return EditorAssignments(assignments=[])

    def fake_polisher_run(**kwargs):
        call_order.append("polisher")
        assert kwargs["plan"].title == "From Director"
        return Storyboard(
            title="Final",
            sections=[StoryboardSection(
                title="S",
                segments=[StoryboardSegment(
                    clip_path=Path("/tmp/clip.mp4"), in_point=0, out_point=5,
                    label="x", transition="cut", include=True,
                )],
            )],
            total_duration=5.0,
            llm_rationale="ok",
        )

    monkeypatch.setattr("vlogkit.storyboard.builder.director.run", fake_director_run)
    monkeypatch.setattr("vlogkit.storyboard.builder.editor.run", fake_editor_run)
    monkeypatch.setattr("vlogkit.storyboard.builder.polisher.run", fake_polisher_run)

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert call_order == ["director", "editor", "polisher"]
    assert sb.title == "Final"


def test_build_storyboard_director_failure_falls_back_to_chronological(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError

    def fake_director_run(**kwargs):
        raise AgentError(stage="director", reason="oops")

    monkeypatch.setattr("vlogkit.storyboard.builder.director.run", fake_director_run)

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    # Fallback used
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_editor_failure_falls_back(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kwargs: DirectorPlan(title="ok", sections=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.editor.run",
        lambda **kwargs: (_ for _ in ()).throw(AgentError(stage="editor", reason="oops")),
    )

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_polisher_failure_falls_back(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kwargs: DirectorPlan(title="ok", sections=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.editor.run",
        lambda **kwargs: EditorAssignments(),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.polisher.run",
        lambda **kwargs: (_ for _ in ()).throw(AgentError(stage="polisher", reason="oops")),
    )

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert sb.sections[0].title == "All Clips (Chronological)"
