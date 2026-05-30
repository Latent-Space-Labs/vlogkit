# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is vlogkit

AI-powered vlog assembly CLI tool. Takes raw video clips, analyzes them (metadata extraction + Whisper transcription), generates an LLM-driven storyboard, and exports NLE-compatible timelines (FCPXML, EDL, OTIO).

## Commands

```bash
# Install (editable, uses hatch build system)
pip install -e .
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
vlogkit captions [-f srt|vtt|ass] [--burn] [-o path]  # Generate captions from the storyboard transcript; --burn renders an MP4 with captions overlaid (needs ffmpeg+libass)
vlogkit tighten [--dry-run] [--render] [-o path]  # Auto-cut silence + filler words from the storyboard; --dry-run previews time saved, --render outputs an MP4
vlogkit render [--captions] [-r 1080p|720p|WxH] [--fps N] [--audio-cleanup] [--denoise] [--title-card TEXT] [--lower-thirds] [-o path]  # Render the storyboard to a finished MP4 (no NLE); normalizes mixed resolutions/fps; --captions bakes captions in (libass); --audio-cleanup loudnorm to -14 LUFS; --title-card / --lower-thirds add text overlays (freetype)
vlogkit chapters [--intro TEXT] [-o path]  # YouTube chapter markers + description from storyboard sections
vlogkit shorts [--min S] [--max S] [--no-captions] [-o path]  # Extract the highest-impact moment as a vertical 9:16 Short with captions
vlogkit highlight [--max S] [--order chronological|score] [-o path]  # Auto-assemble a highlight reel from top-scored scenes
vlogkit thumbnail [-t TITLE] [-n COUNT] [-o dir]  # Thumbnail candidates from the most aesthetic scenes (title overlay needs freetype)
vlogkit preset [NAME] [-p path]  # List or apply a content preset (tutorial|vlog|travel) — bundles strategy + scoring weights + caption style + tighten config
vlogkit broll [-n COUNT]  # Suggest B-roll/cutaway opportunities over narration-heavy stretches
vlogkit index [-p path]      # Build semantic search index (requires [search] deps)
vlogkit search "query"       # Search clips by visual content (e.g. "sunset over bridge")
vlogkit search-stats         # Show search index info
vlogkit serve [path]         # Start upload server for companion app (port 8420)

> **Breaking change (Plan 1):** `vlogkit serve` now requires an auth token on every request. The token is generated at startup and printed on the console — companion apps must send it as `Authorization: Bearer <token>`.

vlogkit server [--port N] [--registry PATH]   # Desktop-mode server (used by the desktop shell)
vlogkit status               # Show project summary
```

## Architecture

**Pipeline flow:** `init` → `analyze` → `storyboard` → `review` → `export`

- **CLI** (`cli.py`): Typer app, all commands delegate to subsystems
- **Project** (`project.py`): State/cache manager. Cache lives in `.vlogkit/` dir. Clip analyses cached by SHA-256 hash prefix — re-analysis skipped if hash matches
- **Models** (`models.py`): All Pydantic models — `ClipMetadata`, `ClipAnalysis`, `Storyboard`, `StoryboardSection`, `StoryboardSegment`, `CaptionCue`, `CaptionStyle`. The `Storyboard` is the central data structure passed between storyboard/review/export stages
- **Edit** (`edit/`): Auto-cut tightening. `detect.py` finds filler words + dead air (word-gap and silence-based) as raw cut ranges. `intervals.py` is pure interval algebra (merge/invert/clamp/filter). `tighten.py` rewrites each included storyboard segment into tighter sub-segments around the cuts and reports before/after `TightenStats`; tuning via `.vlogkit/tighten.json` (`TightenConfig`). Output is an ordinary `Storyboard`, so it flows through export/captions/render
- **ffmpeg_util.py**: Resolves an ffmpeg binary, preferring a libass-capable build for burn-in (Homebrew's regular `ffmpeg` dropped libass; `ffmpeg-full` is keg-only and also carries freetype for drawtext). Honors `VLOGKIT_FFMPEG`
- **Repurpose** (`repurpose/`): `shorts.py` picks the highest-impact 15–60s window and reframes to vertical 9:16 (center-crop fill) with burned captions. `highlight.py` assembles a montage from top-composite-scored scenes. `thumbnail.py` ranks scenes by aesthetic score and renders thumbnail JPGs with an optional drawtext title.
- **Publish** (`publish/`): `chapters.py` maps storyboard sections to YouTube chapter markers (first=0:00, ≥10s spacing) and builds a description block.
- **presets.py**: Named content presets (tutorial/vlog/travel) that write `.vlogkit/{caption_style,tighten,score_weights}.json` and carry a storyboard strategy. `edit/broll.py` suggests B-roll cutaways over narration-heavy stretches using transcript + aesthetic scores (analysis only, no render). Caption animation styles (`pop`, `highlight_box`) live in `captions/formats.py` driven by `CaptionStyle.animation`; audio loudness/denoise + title-card/lower-third overlays are optional params on `captions/render.py`
- **Captions** (`captions/`): Generates captions from the storyboard transcript. `cues.py` remaps Whisper word timestamps onto the final edited timeline and groups them into readable cues (BBC/Netflix rules: ≤42 chars/line, ≤2 lines, ≤6s, break on punctuation/pauses). `formats.py` serializes cues to SRT/VTT/ASS (ASS supports word-level karaoke highlight). `render.py` builds a single-pass ffmpeg `filter_complex` (trim+concat segments, burn ASS subtitles); `build_ffmpeg_command(resolution=...)` scales+pads each segment to a uniform size so mixed-resolution clips concat cleanly, and `pick_render_target()` auto-selects output resolution/fps from the largest source clip. This engine backs both `vlogkit captions --burn` and the first-class `vlogkit render` command. `pipeline.py` ties it together and loads styling overrides from `.vlogkit/caption_style.json`. SRT/VTT/ASS sidecars need no external tools; `--burn` requires an ffmpeg built with libass
- **Analysis** (`analyze/`): `pipeline.py` orchestrates per-clip analysis. `metadata.py` extracts via ffprobe. `transcribe.py` uses faster-whisper. `scenes.py` detects scene cuts. `vision.py` describes keyframes via Claude vision. `audio.py` and `motion.py` do audio/motion analysis. Results cached as JSON in `.vlogkit/clips/`
- **LLM** (`llm/`): `LLMBackend` Protocol with `ClaudeBackend` and `OpenAIBackend` implementations. Falls back to chronological ordering when no API key is set
- **Search** (`search/`): Semantic video search via `sentrysearch` dependency. `indexer.py` chunks clips and embeds via Gemini API into per-project ChromaDB. `query.py` runs natural language queries against the index. Auto-indexes during `analyze` if enabled. Requires `[search]` optional deps
- **Server** (`server/`): FastAPI package with app factory, bearer-token auth, project registry, and route modules (health, projects, clips, media, uploads, analyze, score, storyboard, search, export, captions, tighten, render). `captions`/`tighten` are synchronous; `render` is a long-running job that streams `render.{started,complete,failed}` events over the `/projects/{id}/events` WebSocket (same WsBroker pattern as analyze/score). Two entrypoints: `create_app` (single-project upload mode used by `vlogkit serve`) and `create_desktop_app` (multi-project desktop mode used by `vlogkit server` / `python -m vlogkit.server`). Requires no optional extras — FastAPI and uvicorn are core deps. The OpenAPI schema is snapshot-tested (`tests/server/test_openapi_snapshot.py`); regenerate with `VLOGKIT_UPDATE_SNAPSHOTS=1`.
- **Desktop** (`desktop/`): Electron shell + Next.js renderer. Two npm workspaces — `desktop/electron/` (TypeScript, main + preload) and `desktop/web/` (Next.js 15 static export, React 19, shadcn/ui + DESIGN.md tokens). Launched via `npm run dev` from `desktop/`; spawns `python -m vlogkit.server` as a sidecar with auth token passed via `VLOGKIT_TOKEN` env var. The board tab exposes Captions (format dialog), Tighten (dry-run preview → apply), and Render (resolution + burn-captions, live job progress over the event WS) alongside Export/Regenerate.
- **Storyboard** (`storyboard/`): `builder.py` sends clip analyses to Claude, parses JSON response into `Storyboard`. `strategies.py` has non-LLM fallbacks. `prompts.py` has prompt templates
- **Interactive** (`interactive/markdown.py`): Bidirectional Storyboard ↔ Markdown conversion. Users edit `storyboard.md` then changes are parsed back
- **Export** (`export/`): Converts `Storyboard` → OpenTimelineIO `Timeline` → output format (FCPXML, EDL, Premiere XML, OTIO)

## Configuration

Settings via `pydantic-settings` with `VLOGKIT_` env prefix:
- `VLOGKIT_ANTHROPIC_API_KEY` — required for LLM storyboard generation
- `VLOGKIT_OPENAI_API_KEY` — alternative LLM backend (OpenAI/GPT-4o)
- `VLOGKIT_WHISPER_MODEL` — whisper model size (default: "base")
- `VLOGKIT_FFMPEG` — path to an ffmpeg binary (blank = auto-resolve, preferring a libass build for caption burn-in)
- `VLOGKIT_CLAUDE_MODEL` — Claude model for text (default: claude-sonnet-4-20250514)
- `VLOGKIT_CLAUDE_VISION_MODEL` — Claude model for keyframe description (default: claude-sonnet-4-20250514)
- `VLOGKIT_GEMINI_API_KEY` — required for semantic video search (Gemini Embedding API)
- `VLOGKIT_SEARCH_AUTO_INDEX` — auto-index during `analyze` (default: true)
- `VLOGKIT_SEARCH_CHUNK_DURATION` — seconds per search chunk (default: 30)
- `VLOGKIT_SEARCH_CHUNK_OVERLAP` — overlap between chunks (default: 5)

## Key dependencies

- `typer` (CLI), `pydantic` (models), `faster-whisper` (transcription), `stable-ts` (aligned transcription), `scenedetect` (scene detection), `opentimelineio` (timeline export), `anthropic` (LLM), `openai` (alt LLM), `ffmpeg-python` (video metadata), `rich` (terminal UI), `fastapi`, `uvicorn`, `python-multipart`, `qrcode` (server)
- Optional `[search]`: `sentrysearch` (brings `chromadb`, `google-genai`)
- Requires Python >=3.11
