# Plan 1 — Wire scene detection + vision into `analyze` (PR 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `analyze/scenes.py` and `analyze/vision.py` modules into the analysis pipeline so every cached `ClipAnalysis` has populated `scenes[]` with descriptions and tags. Adds a `--no-vision` opt-out flag on `vlogkit analyze`.

**Architecture:** `analyze_clip()` is extended to call `detect_scenes()` after metadata/transcription, then for each scene extract a keyframe (mid-scene) and call `describe_keyframe()`. Failures in any sub-step are caught and logged but don't abort the whole clip. Cached analyses missing `scenes` are treated as stale when vision is requested, triggering re-analysis.

**Tech Stack:** Python 3.11+, pytest, pydantic, PySceneDetect, ffmpeg, anthropic SDK (existing).

**Spec reference:** `docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md` §3 (pipeline), §6.3 (`--no-vision` flag), §8 PR 1.

---

## File map

- **Create:** `tests/test_pipeline.py` — new unit tests for `analyze_clip` and `run_analysis`
- **Modify:** `src/vlogkit/analyze/pipeline.py` — extend `analyze_clip` and `run_analysis` to wire scenes + vision
- **Modify:** `src/vlogkit/cli.py:43-68` — add `--no-vision` flag to `analyze` command and surface a cost-warning message

No model changes. No config changes. No new packages.

---

## Task 1: Test that `analyze_clip` populates `scenes[]`

**Files:**
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Create the test file with the first failing test**

Create `tests/test_pipeline.py` with the following content:

```python
"""Unit tests for the analysis pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.analyze.pipeline import analyze_clip
from vlogkit.config import Settings
from vlogkit.models import ClipMetadata, SceneSegment


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key")


@pytest.fixture
def stub_metadata_and_transcribe(monkeypatch):
    """Stub metadata extraction + transcription so tests don't need a real video file."""

    def fake_extract(clip_path: Path) -> ClipMetadata:
        return ClipMetadata(
            filename=clip_path.name,
            path=clip_path,
            duration=10.0,
            resolution=(1920, 1080),
            fps=30.0,
            file_size=1024,
        )

    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_metadata", fake_extract)
    monkeypatch.setattr("vlogkit.analyze.pipeline.transcribe_clip", lambda *a, **k: [])


def test_analyze_clip_populates_scenes(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """Detected scenes must be attached to the returned ClipAnalysis."""
    fake_scenes = [
        SceneSegment(start=0.0, end=5.0),
        SceneSegment(start=5.0, end=10.0),
    ]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)
    # Stub vision so this test focuses on scene detection only
    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", lambda *a, **k: tmp_path / "kf.jpg")
    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", lambda *a, **k: ("", []))

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=False, keyframes_dir=tmp_path)

    assert len(result.scenes) == 2
    assert result.scenes[0].start == 0.0
    assert result.scenes[0].end == 5.0
    assert result.scenes[1].start == 5.0
    assert result.scenes[1].end == 10.0
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
pytest tests/test_pipeline.py::test_analyze_clip_populates_scenes -v
```

Expected: FAIL. The current `analyze_clip` signature does not accept `with_vision` or `keyframes_dir`, and does not import `detect_scenes`/`extract_keyframe`/`describe_keyframe`. The failure will be a `TypeError` (unexpected kwarg) or `AttributeError` from monkeypatch (no such attribute on the module).

- [ ] **Step 3: Implement the minimum change to pass this test**

Replace the entire contents of `src/vlogkit/analyze/pipeline.py` with:

```python
"""Analysis pipeline — orchestrates metadata + transcription + scenes + vision with caching."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import Settings
from ..models import ClipAnalysis, SceneSegment
from ..project import Project, file_hash
from .metadata import extract_metadata
from .scenes import detect_scenes, extract_keyframe
from .transcribe import transcribe_clip
from .vision import describe_keyframe

console = Console()


def analyze_clip(
    clip_path: Path,
    settings: Settings,
    with_vision: bool = True,
    keyframes_dir: Path | None = None,
) -> ClipAnalysis:
    metadata = extract_metadata(clip_path)

    transcript = []
    try:
        transcript = transcribe_clip(
            clip_path,
            model_size=settings.whisper_model,
            device=settings.whisper_device,
        )
    except Exception as e:
        console.print(f"  [yellow]Transcription failed for {clip_path.name}: {e}[/]")

    scenes: list[SceneSegment] = []
    try:
        scenes = detect_scenes(clip_path)
    except Exception as e:
        console.print(f"  [yellow]Scene detection failed for {clip_path.name}: {e}[/]")

    full_text = " ".join(seg.text for seg in transcript)
    summary = full_text[:200] + "..." if len(full_text) > 200 else full_text

    return ClipAnalysis(
        metadata=metadata,
        transcript=transcript,
        scenes=scenes,
        summary=summary,
        file_hash=file_hash(clip_path),
    )


def run_analysis(project: Project, force: bool = False, with_vision: bool = True) -> list[ClipAnalysis]:
    clips = project.scan_clips()
    if not clips:
        console.print("[red]No video clips found.[/]")
        return []

    results: list[ClipAnalysis] = []
    keyframes_dir = project.settings.keyframes_dir(project.root)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing clips...", total=len(clips))

        for clip in clips:
            progress.update(task, description=f"Analyzing {clip.name}...")

            if not force:
                cached = project.load_analysis(clip)
                if cached and (not with_vision or cached.scenes):
                    results.append(cached)
                    progress.advance(task)
                    continue

            analysis = analyze_clip(
                clip,
                project.settings,
                with_vision=with_vision,
                keyframes_dir=keyframes_dir,
            )
            project.save_analysis(analysis)
            results.append(analysis)
            progress.advance(task)

    console.print(f"[green]Analyzed {len(results)} clips.[/]")
    return results
```

This change wires `detect_scenes` into `analyze_clip` and threads `with_vision` + `keyframes_dir` through `run_analysis`. Vision is not yet active — it's gated behind `with_vision=True` and a not-yet-implemented call site that will appear in Task 2.

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
pytest tests/test_pipeline.py::test_analyze_clip_populates_scenes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline.py src/vlogkit/analyze/pipeline.py
git commit -m "$(cat <<'EOF'
feat(analyze): detect scenes during clip analysis

Wires PySceneDetect into analyze_clip via the existing scenes.py module
so every ClipAnalysis has populated scenes[]. Adds with_vision and
keyframes_dir parameters in preparation for vision integration. Cached
analyses missing scenes are re-run when vision is requested.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Test that vision step populates description and tags

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `src/vlogkit/analyze/pipeline.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_pipeline.py`:

```python
def test_analyze_clip_vision_populates_descriptions(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """When with_vision=True, each scene gets a description, tags, and a keyframe path."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0), SceneSegment(start=5.0, end=10.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    captured_keyframes: list[Path] = []

    def fake_extract_keyframe(clip_path: Path, timestamp: float, output_path: Path) -> Path:
        output_path.write_bytes(b"fake-jpg")
        captured_keyframes.append(output_path)
        return output_path

    def fake_describe(image_path: str, s: Settings) -> tuple[str, list[str]]:
        return (f"description for {Path(image_path).name}", ["tagA", "tagB"])

    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", fake_extract_keyframe)
    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=True, keyframes_dir=tmp_path)

    assert len(result.scenes) == 2
    for scene in result.scenes:
        assert scene.description.startswith("description for ")
        assert scene.tags == ["tagA", "tagB"]
        assert scene.keyframe_path is not None
        assert scene.keyframe_path.exists()
    assert len(captured_keyframes) == 2
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
pytest tests/test_pipeline.py::test_analyze_clip_vision_populates_descriptions -v
```

Expected: FAIL — assertions like `scene.description.startswith("description for ")` will fail because the current implementation does not call `extract_keyframe` or `describe_keyframe`.

- [ ] **Step 3: Implement vision integration**

In `src/vlogkit/analyze/pipeline.py`, replace the `analyze_clip` function with this version (adds the vision loop, leaves the rest unchanged):

```python
def analyze_clip(
    clip_path: Path,
    settings: Settings,
    with_vision: bool = True,
    keyframes_dir: Path | None = None,
) -> ClipAnalysis:
    metadata = extract_metadata(clip_path)

    transcript = []
    try:
        transcript = transcribe_clip(
            clip_path,
            model_size=settings.whisper_model,
            device=settings.whisper_device,
        )
    except Exception as e:
        console.print(f"  [yellow]Transcription failed for {clip_path.name}: {e}[/]")

    scenes: list[SceneSegment] = []
    try:
        scenes = detect_scenes(clip_path)
    except Exception as e:
        console.print(f"  [yellow]Scene detection failed for {clip_path.name}: {e}[/]")

    if with_vision and scenes and settings.anthropic_api_key:
        kf_dir = keyframes_dir or clip_path.parent
        kf_dir.mkdir(parents=True, exist_ok=True)
        for idx, scene in enumerate(scenes):
            midpoint = (scene.start + scene.end) / 2
            kf_path = kf_dir / f"{clip_path.stem}_scene{idx}.jpg"
            try:
                extract_keyframe(clip_path, midpoint, kf_path)
                scene.keyframe_path = kf_path
                description, tags = describe_keyframe(str(kf_path), settings)
                scene.description = description
                scene.tags = tags
            except Exception as e:
                console.print(f"  [yellow]Vision failed for scene {idx} of {clip_path.name}: {e}[/]")

    full_text = " ".join(seg.text for seg in transcript)
    summary = full_text[:200] + "..." if len(full_text) > 200 else full_text

    return ClipAnalysis(
        metadata=metadata,
        transcript=transcript,
        scenes=scenes,
        summary=summary,
        file_hash=file_hash(clip_path),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
pytest tests/test_pipeline.py::test_analyze_clip_vision_populates_descriptions -v
```

Expected: PASS.

- [ ] **Step 5: Run the full pipeline test file to confirm nothing regressed**

Run:
```bash
pytest tests/test_pipeline.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_pipeline.py src/vlogkit/analyze/pipeline.py
git commit -m "$(cat <<'EOF'
feat(analyze): describe scene keyframes via Claude vision

Extracts a mid-scene keyframe and calls describe_keyframe per scene to
populate SceneSegment.description, tags, and keyframe_path. Skipped
silently when with_vision=False or no API key is set. Vision failures
on individual scenes are logged but don't abort the clip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Test that `with_vision=False` skips vision calls entirely

**Files:**
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_pipeline.py`:

```python
def test_analyze_clip_no_vision_skips_vision_calls(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """When with_vision=False, scenes still detect but vision is never called."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    describe_calls = 0
    extract_calls = 0

    def fake_describe(*a, **k):
        nonlocal describe_calls
        describe_calls += 1
        return ("should not appear", [])

    def fake_extract_keyframe(*a, **k):
        nonlocal extract_calls
        extract_calls += 1
        return Path("nowhere.jpg")

    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)
    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", fake_extract_keyframe)

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=False, keyframes_dir=tmp_path)

    assert len(result.scenes) == 1
    assert result.scenes[0].description == ""
    assert result.scenes[0].tags == []
    assert describe_calls == 0
    assert extract_calls == 0


def test_analyze_clip_no_api_key_skips_vision_even_when_requested(stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """With no API key, vision is skipped even if with_vision=True (graceful degradation)."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    describe_calls = 0

    def fake_describe(*a, **k):
        nonlocal describe_calls
        describe_calls += 1
        return ("should not appear", [])

    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)

    settings_no_key = Settings(anthropic_api_key="")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings_no_key, with_vision=True, keyframes_dir=tmp_path)

    assert len(result.scenes) == 1
    assert describe_calls == 0
```

- [ ] **Step 2: Run the tests**

Run:
```bash
pytest tests/test_pipeline.py -v
```

Expected: both new tests PASS (the implementation from Task 2 already gates vision behind both `with_vision` and `settings.anthropic_api_key`).

If either test FAILS, the gate logic is wrong — fix `analyze_clip` so the condition is `if with_vision and scenes and settings.anthropic_api_key:` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
test(analyze): cover --no-vision and missing-API-key paths

Verifies vision calls are gated behind both with_vision=True and a
non-empty anthropic_api_key. Both gates skip vision without erroring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Test that `run_analysis` threads `with_vision` to `analyze_clip`

**Files:**
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_pipeline.py`:

```python
def test_run_analysis_threads_with_vision_flag(tmp_path, monkeypatch):
    """run_analysis must pass with_vision through to analyze_clip."""
    from vlogkit.analyze import pipeline as pipeline_module
    from vlogkit.project import Project

    # Stub Project.scan_clips to return a single fake clip
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: None)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)

    captured: dict[str, object] = {}

    def fake_analyze_clip(c, s, with_vision=True, keyframes_dir=None):
        captured["with_vision"] = with_vision
        captured["keyframes_dir"] = keyframes_dir
        from vlogkit.models import ClipAnalysis, ClipMetadata

        return ClipAnalysis(
            metadata=ClipMetadata(
                filename=c.name, path=c, duration=1.0, resolution=(1, 1), fps=1.0, file_size=1
            ),
            file_hash="deadbeef",
        )

    monkeypatch.setattr(pipeline_module, "analyze_clip", fake_analyze_clip)

    project = Project(tmp_path)
    pipeline_module.run_analysis(project, force=False, with_vision=False)

    assert captured["with_vision"] is False
    assert captured["keyframes_dir"] is not None
    assert ".vlogkit" in str(captured["keyframes_dir"])
```

- [ ] **Step 2: Run the test**

Run:
```bash
pytest tests/test_pipeline.py::test_run_analysis_threads_with_vision_flag -v
```

Expected: PASS. (The `with_vision` parameter was already added to `run_analysis` in Task 1.) If it fails, check that `run_analysis` accepts `with_vision` and passes it to `analyze_clip`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
test(analyze): verify run_analysis threads with_vision through

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `--no-vision` flag to the `vlogkit analyze` CLI command

**Files:**
- Modify: `src/vlogkit/cli.py:43-68`

- [ ] **Step 1: Write the failing test (CLI flag)**

Append to `tests/test_pipeline.py`:

```python
def test_cli_no_vision_flag_threads_through(tmp_path, monkeypatch):
    """The CLI --no-vision flag must reach run_analysis with with_vision=False."""
    from typer.testing import CliRunner

    from vlogkit.cli import app

    captured: dict[str, object] = {}

    def fake_run_analysis(project, force=False, with_vision=True):
        captured["with_vision"] = with_vision

    monkeypatch.setattr("vlogkit.analyze.pipeline.run_analysis", fake_run_analysis)
    # Prevent the search auto-indexer from touching anything real
    monkeypatch.setattr(
        "vlogkit.search.indexer.index_clips",
        lambda *a, **k: None,
        raising=False,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--no-vision", "-p", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert captured["with_vision"] is False
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
pytest tests/test_pipeline.py::test_cli_no_vision_flag_threads_through -v
```

Expected: FAIL — the CLI doesn't have a `--no-vision` flag yet, so the unknown option causes a non-zero exit.

- [ ] **Step 3: Add the `--no-vision` flag**

In `src/vlogkit/cli.py`, replace the `analyze` command (lines 43–68) with:

```python
@app.command()
def analyze(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-analyze all clips")] = False,
    no_vision: Annotated[bool, typer.Option("--no-vision", help="Skip Claude vision keyframe descriptions")] = False,
):
    """Run analysis pipeline (transcribe, detect scenes, describe keyframes). Results are cached."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    from .analyze.pipeline import run_analysis

    if not no_vision and project.settings.anthropic_api_key:
        clips = project.scan_clips()
        console.print(
            f"[dim]Vision: describing scene keyframes for {len(clips)} clip(s) via Claude "
            f"(~$0.02 per scene; use --no-vision to skip).[/]"
        )

    run_analysis(project, force=force, with_vision=not no_vision)

    # Auto-index for semantic search if enabled and search deps installed
    if project.settings.search_auto_index:
        try:
            from .search.indexer import index_clips

            console.print("\n[bold]Auto-indexing for semantic search...[/]")
            index_clips(project)
        except ImportError:
            pass  # search deps not installed — skip silently
        except Exception as e:
            console.print(f"[yellow]Search indexing failed (non-blocking): {e}[/]")
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
pytest tests/test_pipeline.py::test_cli_no_vision_flag_threads_through -v
```

Expected: PASS.

- [ ] **Step 5: Run the full new test file**

Run:
```bash
pytest tests/test_pipeline.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/cli.py tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
feat(cli): add --no-vision flag to vlogkit analyze

Lets users opt out of the new keyframe-description step (and its cost).
Prints a one-line cost warning when vision is active so users see what
they're paying for. Default behavior: vision on.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Verify nothing else broke

**Files:**
- None modified

- [ ] **Step 1: Run the whole test suite**

Run:
```bash
pytest -v
```

Expected: all existing tests + 5 new ones PASS. The existing tests touch models, markdown, search, strategies, and server — none of which depend on `analyze_clip`'s signature, so they should still pass. If anything fails, read the failure and decide whether it's a real regression or a test that mocked the old `analyze_clip` signature.

- [ ] **Step 2: If a regression is found, fix it inline**

The most likely failure path: a test that imports `analyze_clip` and calls it with the old two-positional-args signature. Since the new signature adds keyword args with defaults, this should be backward-compatible — but verify. If a real regression exists, fix `analyze/pipeline.py` to preserve the old behavior under the old signature and re-run.

- [ ] **Step 3: Commit (if any fixes were needed)**

If Step 2 required changes:
```bash
git add <files-changed>
git commit -m "$(cat <<'EOF'
fix(analyze): preserve backward compatibility for analyze_clip callers

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no fixes were needed, skip this commit.

---

## Task 7: Manual smoke test on a real project

This task verifies the change works end-to-end against actual video. Do this before opening the PR.

**Files:**
- None modified

- [ ] **Step 1: Set up a tiny smoke-test project**

In a directory containing 1-2 real short video clips (≤ 30 s each), run:

```bash
cd /tmp/smoke-test            # or wherever your test clips live
vlogkit init
```

Expected: `Initialized vlogkit project ...` + clip count.

- [ ] **Step 2: Run analyze with vision off (cheap path)**

```bash
vlogkit analyze --no-vision --force
```

Expected output includes per-clip progress and `Analyzed N clips`. After completion, inspect a cache file:

```bash
cat .vlogkit/clips/*.json | head -80
```

Expected: `scenes` is a non-empty list with `start`/`end` populated; `description` is empty; `tags` is empty.

- [ ] **Step 3: Run analyze with vision on (paid path)**

Ensure `VLOGKIT_ANTHROPIC_API_KEY` is set, then:

```bash
vlogkit analyze --force
```

Expected output includes the cost-warning message, per-clip progress, and `Analyzed N clips`. Inspect a cache file:

```bash
cat .vlogkit/clips/*.json | head -80
```

Expected: `scenes` entries now have non-empty `description` and `tags`, and `keyframe_path` points to a real `.vlogkit/keyframes/*.jpg` file. Confirm the keyframe images exist:

```bash
ls .vlogkit/keyframes/
```

- [ ] **Step 4: Confirm `vlogkit status` still works**

```bash
vlogkit status
```

Expected: status table shows the analyzed clip count.

- [ ] **Step 5: If anything looks wrong, capture the failure and STOP**

If scenes are empty, descriptions don't appear, or the CLI errors out, do not push the PR. Reproduce the failure with `pytest` if possible (which means the test coverage above missed a case) and fix.

---

## Task 8: Open the PR

- [ ] **Step 1: Push the branch and open PR**

```bash
git push -u origin claude/loving-chatterjee-4a0ad1
gh pr create --title "feat(analyze): wire scene detection + vision into analyze" --body "$(cat <<'EOF'
## Summary
- Wires `analyze/scenes.py` and `analyze/vision.py` into the analysis pipeline so every cached `ClipAnalysis` has populated `scenes[]` with descriptions, tags, and keyframe paths.
- Adds a `--no-vision` flag on `vlogkit analyze` for users who want to skip the new Claude vision cost.
- Prints a one-line cost-warning message when vision is active.
- Cached analyses missing `scenes` are treated as stale and re-run automatically when vision is requested.

This is **PR 1 of 3** in the Murch-scoring + multi-agent-storyboard rollout (spec: `docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md`). PR 2 will add `vlogkit score`; PR 3 will refactor storyboard generation into a Director→Editor→Polisher pipeline.

## Test plan
- [x] Unit tests cover: scene detection wiring, vision wiring, --no-vision flag, missing-API-key gating, CLI flag threading
- [x] Manual smoke test against real clips (with and without --no-vision)
- [x] Existing test suite passes unchanged

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Capture the PR URL**

`gh pr create` will print the URL. Save it — you'll reference it when starting Plan 2.

---

## Self-review checklist (do this before declaring Plan 1 done)

- [ ] Every step has actual code / commands, no placeholders
- [ ] `analyze_clip` signature is consistent across all tasks: `(clip_path, settings, with_vision=True, keyframes_dir=None)`
- [ ] `run_analysis` signature is consistent: `(project, force=False, with_vision=True)`
- [ ] All 5 new tests refer to functions and classes that exist after the preceding tasks run
- [ ] The plan covers everything in spec §3 row 1 (`analyze` extended), §6.3 (`--no-vision`), §8 PR 1
- [ ] Commits are small, each focused on one logical change
