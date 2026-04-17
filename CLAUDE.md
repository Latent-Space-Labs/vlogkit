# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is vlogkit

AI-powered vlog assembly CLI tool. Takes raw video clips, analyzes them (metadata extraction + Whisper transcription), generates an LLM-driven storyboard, and exports NLE-compatible timelines (FCPXML, EDL, OTIO).

## Commands

```bash
# Install (editable, uses hatch build system)
pip install -e .
pip install -e '.[server]'   # Include upload server deps (FastAPI, uvicorn, qrcode)
pip install -e '.[search]'  # Include semantic video search (sentrysearch, chromadb)

# Run tests
pytest

# Run a single test
pytest tests/test_models.py::test_storyboard_included_duration

# CLI usage
vlogkit init [path]          # Scan directory for video clips
vlogkit analyze [-p path]    # Transcribe + extract metadata (cached)
vlogkit storyboard [-s strategy] [-c context]  # LLM storyboard generation
vlogkit review               # Open storyboard.md in $EDITOR
vlogkit export [-f format]   # Export to NLE format (fcpxml|edl|premiere|otio)
vlogkit index [-p path]      # Build semantic search index (requires [search] deps)
vlogkit search "query"       # Search clips by visual content (e.g. "sunset over bridge")
vlogkit search-stats         # Show search index info
vlogkit serve [path]         # Start upload server for companion app (port 8420)
vlogkit server [--port N] [--registry PATH]   # Desktop-mode server (used by the desktop shell)
vlogkit status               # Show project summary
```

## Architecture

**Pipeline flow:** `init` → `analyze` → `storyboard` → `review` → `export`

- **CLI** (`cli.py`): Typer app, all commands delegate to subsystems
- **Project** (`project.py`): State/cache manager. Cache lives in `.vlogkit/` dir. Clip analyses cached by SHA-256 hash prefix — re-analysis skipped if hash matches
- **Models** (`models.py`): All Pydantic models — `ClipMetadata`, `ClipAnalysis`, `Storyboard`, `StoryboardSection`, `StoryboardSegment`. The `Storyboard` is the central data structure passed between storyboard/review/export stages
- **Analysis** (`analyze/`): `pipeline.py` orchestrates per-clip analysis. `metadata.py` extracts via ffprobe. `transcribe.py` uses faster-whisper. `scenes.py` detects scene cuts. `vision.py` describes keyframes via Claude vision. `audio.py` and `motion.py` do audio/motion analysis. Results cached as JSON in `.vlogkit/clips/`
- **LLM** (`llm/`): `LLMBackend` Protocol with `ClaudeBackend` and `OpenAIBackend` implementations. Falls back to chronological ordering when no API key is set
- **Search** (`search/`): Semantic video search via `sentrysearch` dependency. `indexer.py` chunks clips and embeds via Gemini API into per-project ChromaDB. `query.py` runs natural language queries against the index. Auto-indexes during `analyze` if enabled. Requires `[search]` optional deps
- **Server** (`server/`): FastAPI package with app factory, bearer-token auth, project registry, and route modules (health, projects, clips, media, uploads). Two entrypoints: `create_app` (single-project upload mode used by `vlogkit serve`) and `create_desktop_app` (multi-project desktop mode used by `vlogkit server` / `python -m vlogkit.server`). Requires no optional extras — FastAPI and uvicorn are core deps.
- **Storyboard** (`storyboard/`): `builder.py` sends clip analyses to Claude, parses JSON response into `Storyboard`. `strategies.py` has non-LLM fallbacks. `prompts.py` has prompt templates
- **Interactive** (`interactive/markdown.py`): Bidirectional Storyboard ↔ Markdown conversion. Users edit `storyboard.md` then changes are parsed back
- **Export** (`export/`): Converts `Storyboard` → OpenTimelineIO `Timeline` → output format (FCPXML, EDL, Premiere XML, OTIO)

## Configuration

Settings via `pydantic-settings` with `VLOGKIT_` env prefix:
- `VLOGKIT_ANTHROPIC_API_KEY` — required for LLM storyboard generation
- `VLOGKIT_OPENAI_API_KEY` — alternative LLM backend (OpenAI/GPT-4o)
- `VLOGKIT_WHISPER_MODEL` — whisper model size (default: "base")
- `VLOGKIT_CLAUDE_MODEL` — Claude model for text (default: claude-sonnet-4-20250514)
- `VLOGKIT_CLAUDE_VISION_MODEL` — Claude model for keyframe description (default: claude-sonnet-4-20250514)
- `VLOGKIT_GEMINI_API_KEY` — required for semantic video search (Gemini Embedding API)
- `VLOGKIT_SEARCH_AUTO_INDEX` — auto-index during `analyze` (default: true)
- `VLOGKIT_SEARCH_CHUNK_DURATION` — seconds per search chunk (default: 30)
- `VLOGKIT_SEARCH_CHUNK_OVERLAP` — overlap between chunks (default: 5)

## Key dependencies

- `typer` (CLI), `pydantic` (models), `faster-whisper` (transcription), `stable-ts` (aligned transcription), `scenedetect` (scene detection), `opentimelineio` (timeline export), `anthropic` (LLM), `openai` (alt LLM), `ffmpeg-python` (video metadata), `rich` (terminal UI)
- Optional `[search]`: `sentrysearch` (brings `chromadb`, `google-genai`)
- Optional `[server]`: `fastapi`, `uvicorn`, `python-multipart`, `qrcode`
- Requires Python >=3.11
