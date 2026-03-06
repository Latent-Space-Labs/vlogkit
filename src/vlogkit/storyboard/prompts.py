"""LLM prompt templates for storyboarding."""

SYSTEM_PROMPT = """\
You are an expert video editor assistant. You analyze raw video clip metadata \
and transcripts, then arrange them into a compelling vlog narrative.

You output structured JSON only — no markdown, no explanation outside the JSON."""

STORYBOARD_PROMPT = """\
I have {clip_count} raw video clips from "{context}". \
Analyze the clips below and create a storyboard that arranges them into a \
compelling vlog with a natural narrative arc.

Guidelines:
- Group clips into logical sections (e.g., "Morning Hike", "Beach Afternoon")
- Order clips to create a narrative flow — establish setting, build energy, resolve
- Set in/out points to trim dead air, shaky starts, and trailing silence
- Mark low-value clips as excluded (include: false)
- Write a short label for each segment describing what viewers see
- Provide a brief rationale for your editing choices

Strategy: {strategy}

Clips:
{clips_json}

Respond with valid JSON matching this schema:
{{
  "title": "string",
  "sections": [
    {{
      "title": "string",
      "notes": "string",
      "segments": [
        {{
          "clip_path": "string (filename)",
          "in_point": float,
          "out_point": float,
          "label": "string",
          "transition": "cut|dissolve|fade",
          "include": bool
        }}
      ]
    }}
  ],
  "total_duration": float,
  "llm_rationale": "string"
}}"""

STRATEGY_HINTS = {
    "chronological": "Arrange clips in chronological order based on creation time. Simple, diary-style vlog.",
    "energy-arc": "Build an energy arc: calm opening, rising action, peak energy moment, wind down. Classic vlog structure.",
    "thematic": "Group clips by theme/location/activity rather than time. Create thematic sections.",
}
