"""Prompt templates for Murch-style scene scoring."""

SYSTEM_PROMPT = """\
You are a video editor scoring scenes for use in a vlog.

Given a scene's description, transcript, duration, and surrounding context, \
classify its narrative role and rate it on five dimensions. \
Return strict JSON only — no markdown, no preamble, no explanation outside the JSON."""


SCORING_PROMPT = """\
Score this scene from a video clip:

Scene {scene_index} of {scene_count} in clip "{clip_filename}"
Time: {start:.1f}s – {end:.1f}s ({duration:.1f}s)
Visual description: {description}
Tags: {tags}
Transcript: {transcript}
Previous scene description: {prev_description}
Next scene description: {next_description}

Classify scene_type as ONE of:
- "hook": opens or grabs attention (big reveal, dramatic shot, peak energy)
- "narrative": carries the story (spoken setup, transitional action, exposition)
- "aesthetic": b-roll / atmosphere (landscape, food close-up, ambient detail)
- "commercial": direct-to-camera, product/promo style (talking head pitch)

Score these five dimensions on 0-100:
- aesthetic: visual composition, lighting, framing
- credibility: authenticity and narrative-supporting feel
- impact: emotional punch, attention-grabbing power
- memorability: would a viewer remember this 10 minutes later
- fun: entertainment / delight factor

Respond with valid JSON exactly matching this schema:
{{
  "scene_type": "hook|narrative|aesthetic|commercial",
  "aesthetic": 0,
  "credibility": 0,
  "impact": 0,
  "memorability": 0,
  "fun": 0,
  "rationale": "one-line justification (under 20 words)"
}}"""
