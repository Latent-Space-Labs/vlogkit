"""Tests for caption serialization formats (SRT, VTT, ASS)."""

from vlogkit.models import CaptionCue, CaptionStyle, WordTimestamp
from vlogkit.captions.formats import (
    _ass_timestamp,
    _hex_to_ass_color,
    _srt_timestamp,
    cues_to_ass,
    cues_to_srt,
    cues_to_vtt,
)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


def _cue(start, end, text, words=None):
    return CaptionCue(start=start, end=end, text=text, words=words or [])


def _word(start, end, word):
    return WordTimestamp(start=start, end=end, word=word)


# --------------------------------------------------------------------------
# _srt_timestamp
# --------------------------------------------------------------------------


def test_srt_timestamp_zero():
    assert _srt_timestamp(0) == "00:00:00,000"


def test_srt_timestamp_milliseconds():
    assert _srt_timestamp(1.5) == "00:00:01,500"


def test_srt_timestamp_hours_minutes_seconds():
    # 1h 2m 3.456s
    assert _srt_timestamp(3723.456) == "01:02:03,456"


def test_srt_timestamp_ms_rounding():
    assert _srt_timestamp(2.001) == "00:00:02,001"


# --------------------------------------------------------------------------
# cues_to_srt
# --------------------------------------------------------------------------


def test_srt_single_cue_exact():
    cues = [_cue(0.0, 1.5, "Hello world")]
    expected = "1\n00:00:00,000 --> 00:00:01,500\nHello world\n\n"
    assert cues_to_srt(cues) == expected


def test_srt_sequential_indices():
    cues = [
        _cue(0.0, 1.0, "one"),
        _cue(1.0, 2.0, "two"),
        _cue(2.0, 3.0, "three"),
    ]
    out = cues_to_srt(cues)
    lines = out.splitlines()
    assert lines[0] == "1"
    assert lines[4] == "2"
    assert lines[8] == "3"


def test_srt_multiline_preserved():
    cues = [_cue(0.0, 2.0, "line one\nline two")]
    out = cues_to_srt(cues)
    assert "line one\nline two" in out
    expected = "1\n00:00:00,000 --> 00:00:02,000\nline one\nline two\n\n"
    assert out == expected


def test_srt_blank_line_between_entries():
    cues = [_cue(0.0, 1.0, "a"), _cue(1.0, 2.0, "b")]
    out = cues_to_srt(cues)
    # entries separated by a blank line
    assert "a\n\n2\n" in out


def test_srt_empty():
    assert cues_to_srt([]) == ""


# --------------------------------------------------------------------------
# cues_to_vtt
# --------------------------------------------------------------------------


def test_vtt_header():
    out = cues_to_vtt([])
    assert out.startswith("WEBVTT\n\n")


def test_vtt_dot_decimal_timestamps():
    cues = [_cue(0.0, 1.5, "Hello")]
    out = cues_to_vtt(cues)
    assert "00:00:00.000 --> 00:00:01.500" in out
    # must NOT use comma decimals
    assert "," not in out


def test_vtt_cue_text_and_blank_line():
    cues = [_cue(0.0, 1.0, "a"), _cue(1.0, 2.0, "b")]
    out = cues_to_vtt(cues)
    assert out.startswith("WEBVTT\n\n")
    assert "a\n\n" in out
    assert "b" in out


def test_vtt_multiline_preserved():
    cues = [_cue(0.0, 2.0, "top\nbottom")]
    out = cues_to_vtt(cues)
    assert "top\nbottom" in out


# --------------------------------------------------------------------------
# _hex_to_ass_color
# --------------------------------------------------------------------------


def test_hex_to_ass_color_highlight():
    # #FFE000 -> R=FF G=E0 B=00 -> &HAABBGGRR = &H0000E0FF
    assert _hex_to_ass_color("#FFE000") == "&H0000E0FF"


def test_hex_to_ass_color_white():
    assert _hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"


def test_hex_to_ass_color_black():
    assert _hex_to_ass_color("#000000") == "&H00000000"


def test_hex_to_ass_color_pure_red():
    # R=FF G=00 B=00 -> &H000000FF
    assert _hex_to_ass_color("#FF0000") == "&H000000FF"


def test_hex_to_ass_color_pure_blue():
    # R=00 G=00 B=FF -> &H00FF0000
    assert _hex_to_ass_color("#0000FF") == "&H00FF0000"


def test_hex_to_ass_color_alpha():
    assert _hex_to_ass_color("#FFFFFF", alpha=128) == "&H80FFFFFF"


def test_hex_to_ass_color_without_hash():
    assert _hex_to_ass_color("FFE000") == "&H0000E0FF"


# --------------------------------------------------------------------------
# _ass_timestamp
# --------------------------------------------------------------------------


def test_ass_timestamp_zero():
    assert _ass_timestamp(0) == "0:00:00.00"


def test_ass_timestamp_centiseconds():
    assert _ass_timestamp(1.5) == "0:00:01.50"


def test_ass_timestamp_hours():
    # 1h 2m 3.45s -> one leading hour digit
    assert _ass_timestamp(3723.45) == "1:02:03.45"


def test_ass_timestamp_centisecond_rounding():
    assert _ass_timestamp(2.01) == "0:00:02.01"


# --------------------------------------------------------------------------
# cues_to_ass structure
# --------------------------------------------------------------------------


def test_ass_has_sections():
    out = cues_to_ass([_cue(0.0, 1.0, "hi")], CaptionStyle())
    assert "[Script Info]" in out
    assert "[V4+ Styles]" in out
    assert "[Events]" in out


def test_ass_script_info_fields():
    out = cues_to_ass([], CaptionStyle())
    assert "ScriptType: v4.00+" in out
    assert "PlayResX: 1920" in out
    assert "PlayResY: 1080" in out
    assert "WrapStyle: 0" in out


def test_ass_style_format_and_default_line():
    out = cues_to_ass([], CaptionStyle())
    assert "Format: Name, Fontname" in out
    # one Default style line
    style_lines = [ln for ln in out.splitlines() if ln.startswith("Style: ")]
    assert len(style_lines) == 1
    assert style_lines[0].startswith("Style: Default,")


def test_ass_style_uses_font_and_colors():
    style = CaptionStyle(font="Impact", font_size=72)
    out = cues_to_ass([], style)
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    assert "Impact" in style_line
    assert "72" in style_line
    # primary white, secondary highlight, outline black
    assert "&H00FFFFFF" in style_line  # PrimaryColour
    assert "&H0000E0FF" in style_line  # SecondaryColour (#FFE000)
    assert "&H00000000" in style_line  # OutlineColour / BackColour


def test_ass_border_style_one():
    out = cues_to_ass([], CaptionStyle())
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    fields = style_line[len("Style: "):].split(",")
    # BorderStyle field present as "1" somewhere; check explicit by reconstructing
    assert "1" in fields


def test_ass_alignment_bottom():
    out = cues_to_ass([], CaptionStyle(position="bottom"))
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    # Alignment 2 for bottom
    assert ",2," in style_line


def test_ass_alignment_center():
    out = cues_to_ass([], CaptionStyle(position="center"))
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    assert ",5," in style_line


def test_ass_alignment_top():
    out = cues_to_ass([], CaptionStyle(position="top"))
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    assert ",8," in style_line


def test_ass_margin_v():
    out = cues_to_ass([], CaptionStyle(margin_v=90))
    style_line = [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]
    assert ",90," in style_line


def test_ass_events_format_line():
    out = cues_to_ass([_cue(0.0, 1.0, "hi")], CaptionStyle())
    assert "Format: Layer, Start, End, Style" in out


def test_ass_dialogue_line():
    out = cues_to_ass([_cue(0.0, 1.5, "Hello")], CaptionStyle())
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")]
    assert len(dlg) == 1
    assert "0:00:00.00" in dlg[0]
    assert "0:00:01.50" in dlg[0]
    assert dlg[0].endswith("Hello")
    assert "Default" in dlg[0]


def test_ass_newline_to_hard_break():
    out = cues_to_ass([_cue(0.0, 1.0, "top\nbottom")], CaptionStyle())
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]
    assert "top\\Nbottom" in dlg
    # the dialogue line itself stays on one physical line
    assert "\n" not in dlg


# --------------------------------------------------------------------------
# Karaoke
# --------------------------------------------------------------------------


def test_ass_karaoke_tags_present_when_enabled():
    words = [_word(0.0, 0.5, "Hello"), _word(0.5, 1.2, "world")]
    cue = _cue(0.0, 1.2, "Hello world", words=words)
    out = cues_to_ass([cue], CaptionStyle(karaoke=True))
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]
    # 0.5s -> 50cs, 0.7s -> 70cs
    assert "{\\k50}Hello" in dlg
    assert "{\\k70}world" in dlg


def test_ass_karaoke_absent_when_disabled():
    words = [_word(0.0, 0.5, "Hello"), _word(0.5, 1.2, "world")]
    cue = _cue(0.0, 1.2, "Hello world", words=words)
    out = cues_to_ass([cue], CaptionStyle(karaoke=False))
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]
    assert "\\k" not in dlg
    assert dlg.endswith("Hello world")


def test_ass_karaoke_absent_when_no_words():
    cue = _cue(0.0, 1.2, "Hello world", words=[])
    out = cues_to_ass([cue], CaptionStyle(karaoke=True))
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]
    assert "\\k" not in dlg
    assert dlg.endswith("Hello world")


def test_ass_karaoke_word_order_preserved():
    words = [_word(0.0, 0.2, "a"), _word(0.2, 0.4, "b"), _word(0.4, 0.6, "c")]
    cue = _cue(0.0, 0.6, "a b c", words=words)
    out = cues_to_ass([cue], CaptionStyle(karaoke=True))
    dlg = [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]
    idx_a = dlg.index("}a")
    idx_b = dlg.index("}b")
    idx_c = dlg.index("}c")
    assert idx_a < idx_b < idx_c
