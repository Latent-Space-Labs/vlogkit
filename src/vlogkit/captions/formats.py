"""Serialize :class:`CaptionCue` lists into subtitle/caption file formats.

Three pure, side-effect-free serializers:

* :func:`cues_to_srt`  -- SubRip (``.srt``)
* :func:`cues_to_vtt`  -- WebVTT (``.vtt``)
* :func:`cues_to_ass`  -- Advanced SubStation Alpha (``.ass``, what ffmpeg burns in)
"""

from __future__ import annotations

from vlogkit.models import CaptionCue, CaptionStyle

__all__ = ["cues_to_srt", "cues_to_vtt", "cues_to_ass"]


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def _split_hms(seconds: float) -> tuple[int, int, int, float]:
    """Split a duration in seconds into (hours, minutes, seconds, fraction)."""
    if seconds < 0:
        seconds = 0.0
    total_seconds = int(seconds)
    frac = seconds - total_seconds
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return hours, minutes, secs, frac


def _srt_timestamp(seconds: float) -> str:
    """Format ``seconds`` as an SRT timestamp ``HH:MM:SS,mmm`` (comma decimal)."""
    hours, minutes, secs, frac = _split_hms(seconds)
    millis = int(round(frac * 1000))
    # Handle rounding spilling into the next second.
    if millis == 1000:
        millis = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _vtt_timestamp(seconds: float) -> str:
    """Format ``seconds`` as a WebVTT timestamp ``HH:MM:SS.mmm`` (dot decimal)."""
    return _srt_timestamp(seconds).replace(",", ".")


def _ass_timestamp(seconds: float) -> str:
    """Format ``seconds`` as an ASS timestamp ``H:MM:SS.cc`` (centiseconds)."""
    hours, minutes, secs, frac = _split_hms(seconds)
    centis = int(round(frac * 100))
    if centis == 100:
        centis = 0
        secs += 1
        if secs == 60:
            secs = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


# ---------------------------------------------------------------------------
# Colour helper
# ---------------------------------------------------------------------------


def _hex_to_ass_color(hex: str, alpha: int = 0) -> str:
    """Convert ``#RRGGBB`` to an ASS ``&HAABBGGRR`` colour string.

    ASS stores colours byte-reversed from RGB with a leading alpha byte where
    ``00`` is fully opaque. e.g. ``"#FFE000"`` -> ``"&H0000E0FF"``.
    """
    value = hex.lstrip("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return f"&H{alpha & 0xFF:02X}{b:02X}{g:02X}{r:02X}"


# ---------------------------------------------------------------------------
# SRT
# ---------------------------------------------------------------------------


def cues_to_srt(cues: list[CaptionCue]) -> str:
    """Serialize cues to SubRip (``.srt``) text."""
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        timing = f"{_srt_timestamp(cue.start)} --> {_srt_timestamp(cue.end)}"
        blocks.append(f"{index}\n{timing}\n{cue.text}\n")
    return "\n".join(blocks) + ("\n" if blocks else "")


# ---------------------------------------------------------------------------
# WebVTT
# ---------------------------------------------------------------------------


def cues_to_vtt(cues: list[CaptionCue]) -> str:
    """Serialize cues to WebVTT (``.vtt``) text."""
    out = "WEBVTT\n\n"
    blocks: list[str] = []
    for cue in cues:
        timing = f"{_vtt_timestamp(cue.start)} --> {_vtt_timestamp(cue.end)}"
        blocks.append(f"{timing}\n{cue.text}\n")
    if blocks:
        out += "\n".join(blocks) + "\n"
    return out


# ---------------------------------------------------------------------------
# ASS (Advanced SubStation Alpha)
# ---------------------------------------------------------------------------


_ALIGNMENT = {"bottom": 2, "center": 5, "top": 8}

_STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding"
)

_EVENT_FORMAT = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
    "Effect, Text"
)


def _animation_prefix(style: CaptionStyle) -> str:
    """Return the per-Dialogue libass override-tag prefix for the animation.

    * ``"none"`` / ``"highlight_box"`` -> ``""`` (no per-line tag; highlight_box
      is realised entirely in the Style line via ``BorderStyle``).
    * ``"pop"`` -> a quick scale-in: start the text at 60% size and animate to
      100% over the first 120ms.
    """
    if style.animation == "pop":
        return "{\\fscx60\\fscy60\\t(0,120,\\fscx100\\fscy100)}"
    return ""


def _ass_dialogue_text(cue: CaptionCue, style: CaptionStyle) -> str:
    """Build the Dialogue text body, applying karaoke tags when requested."""
    if style.karaoke and cue.words:
        parts: list[str] = []
        for word in cue.words:
            centis = int(round((word.end - word.start) * 100))
            parts.append(f"{{\\k{centis}}}{word.word} ")
        text = "".join(parts).rstrip(" ")
    else:
        text = cue.text
    return text.replace("\n", "\\N")


def cues_to_ass(cues: list[CaptionCue], style: CaptionStyle) -> str:
    """Serialize cues to Advanced SubStation Alpha (``.ass``) text."""
    primary = _hex_to_ass_color(style.primary_color)
    secondary = _hex_to_ass_color(style.highlight_color)
    outline = _hex_to_ass_color(style.outline_color)
    alignment = _ALIGNMENT[style.position]

    # highlight_box draws the text on an opaque box: BorderStyle=3 turns the
    # outline+shadow rectangle into a filled box, and BackColour becomes the box
    # fill (we use the highlight colour). For "none" and "pop" the style section
    # must remain byte-identical to legacy output (BorderStyle=1, outline back).
    if style.animation == "highlight_box":
        border_style = "3"
        back_colour = secondary  # highlight_color, used as the box fill
    else:
        border_style = "1"
        back_colour = outline

    style_fields = [
        "Default",                 # Name
        style.font,                # Fontname
        str(style.font_size),      # Fontsize
        primary,                   # PrimaryColour
        secondary,                 # SecondaryColour
        outline,                   # OutlineColour
        back_colour,               # BackColour
        "0",                       # Bold
        "0",                       # Italic
        "0",                       # Underline
        "0",                       # StrikeOut
        "100",                     # ScaleX
        "100",                     # ScaleY
        "0",                       # Spacing
        "0",                       # Angle
        border_style,              # BorderStyle
        _fmt_num(style.outline),   # Outline
        _fmt_num(style.shadow),    # Shadow
        str(alignment),            # Alignment
        "10",                      # MarginL
        "10",                      # MarginR
        str(style.margin_v),       # MarginV
        "1",                       # Encoding
    ]
    style_line = "Style: " + ",".join(style_fields)

    lines: list[str] = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        _STYLE_FORMAT,
        style_line,
        "",
        "[Events]",
        _EVENT_FORMAT,
    ]

    prefix = _animation_prefix(style)
    for cue in cues:
        text = prefix + _ass_dialogue_text(cue, style)
        dialogue = (
            f"Dialogue: 0,{_ass_timestamp(cue.start)},{_ass_timestamp(cue.end)},"
            f"Default,,0,0,0,,{text}"
        )
        lines.append(dialogue)

    return "\n".join(lines) + "\n"


def _fmt_num(value: float) -> str:
    """Render a float without a trailing ``.0`` for whole numbers."""
    if value == int(value):
        return str(int(value))
    return str(value)
