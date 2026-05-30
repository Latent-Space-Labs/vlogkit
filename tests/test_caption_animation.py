"""Tests for animated caption styles in ASS output.

Covers the ``CaptionStyle.animation`` field: ``"none"`` (default, must be
byte-identical to legacy output), ``"pop"`` (scale-in prefix), and
``"highlight_box"`` (opaque box via BorderStyle=3).
"""

from vlogkit.models import CaptionCue, CaptionStyle, WordTimestamp
from vlogkit.captions.formats import cues_to_ass, _animation_prefix


def _cue(start, end, text, words=None):
    return CaptionCue(start=start, end=end, text=text, words=words or [])


def _word(start, end, word):
    return WordTimestamp(start=start, end=end, word=word)


def _style_line(out: str) -> str:
    return [ln for ln in out.splitlines() if ln.startswith("Style: Default,")][0]


def _dialogue(out: str) -> str:
    return [ln for ln in out.splitlines() if ln.startswith("Dialogue: ")][0]


# --------------------------------------------------------------------------
# _animation_prefix helper
# --------------------------------------------------------------------------


def test_animation_prefix_none_is_empty():
    assert _animation_prefix(CaptionStyle(animation="none")) == ""


def test_animation_prefix_highlight_box_is_empty():
    # highlight_box is handled in the Style line, not via a per-line prefix.
    assert _animation_prefix(CaptionStyle(animation="highlight_box")) == ""


def test_animation_prefix_pop_is_scale_tag():
    prefix = _animation_prefix(CaptionStyle(animation="pop"))
    assert prefix == "{\\fscx60\\fscy60\\t(0,120,\\fscx100\\fscy100)}"


# --------------------------------------------------------------------------
# animation="none" -- no regression
# --------------------------------------------------------------------------


def test_none_output_identical_to_default():
    cues = [_cue(0.0, 1.5, "Hello")]
    assert cues_to_ass(cues, CaptionStyle()) == cues_to_ass(
        cues, CaptionStyle(animation="none")
    )


def test_none_dialogue_unchanged():
    out = cues_to_ass([_cue(0.0, 1.5, "Hello")], CaptionStyle(animation="none"))
    dlg = _dialogue(out)
    assert dlg.endswith("Hello")
    assert "\\fscx" not in dlg
    assert "\\t(" not in dlg


def test_none_border_style_one():
    out = cues_to_ass([], CaptionStyle(animation="none"))
    fields = _style_line(out)[len("Style: "):].split(",")
    assert fields[15] == "1"  # BorderStyle


# --------------------------------------------------------------------------
# animation="pop"
# --------------------------------------------------------------------------


def test_pop_dialogue_has_scale_tags():
    out = cues_to_ass([_cue(0.0, 1.5, "Hello")], CaptionStyle(animation="pop"))
    dlg = _dialogue(out)
    assert "\\t(" in dlg
    assert "\\fscx60" in dlg
    assert "\\fscy60" in dlg
    assert "\\fscx100" in dlg
    # text still present after the prefix
    assert dlg.endswith("Hello")


def test_pop_border_style_unchanged():
    out = cues_to_ass([], CaptionStyle(animation="pop"))
    fields = _style_line(out)[len("Style: "):].split(",")
    assert fields[15] == "1"  # BorderStyle still outline


def test_pop_style_section_identical_to_none():
    # [V4+ Styles] must be identical for none and pop.
    none_out = cues_to_ass([], CaptionStyle(animation="none"))
    pop_out = cues_to_ass([], CaptionStyle(animation="pop"))
    assert _style_line(none_out) == _style_line(pop_out)


# --------------------------------------------------------------------------
# animation="highlight_box"
# --------------------------------------------------------------------------


def test_highlight_box_border_style_three():
    out = cues_to_ass([], CaptionStyle(animation="highlight_box"))
    fields = _style_line(out)[len("Style: "):].split(",")
    assert fields[15] == "3"  # BorderStyle = opaque box


def test_highlight_box_uses_highlight_colour_as_box():
    style = CaptionStyle(animation="highlight_box", highlight_color="#FFE000")
    out = cues_to_ass([], style)
    fields = _style_line(out)[len("Style: "):].split(",")
    # BackColour (index 6) is the box colour -> highlight colour.
    assert fields[6] == "&H0000E0FF"


def test_highlight_box_no_per_line_prefix():
    out = cues_to_ass([_cue(0.0, 1.5, "Hello")], CaptionStyle(animation="highlight_box"))
    dlg = _dialogue(out)
    assert dlg.endswith("Hello")
    assert "\\fscx" not in dlg


def test_highlight_box_diverges_from_none():
    none_out = cues_to_ass([], CaptionStyle(animation="none"))
    box_out = cues_to_ass([], CaptionStyle(animation="highlight_box"))
    assert _style_line(none_out) != _style_line(box_out)


# --------------------------------------------------------------------------
# pop + karaoke together
# --------------------------------------------------------------------------


def test_pop_with_karaoke_prefix_before_k_tags():
    words = [_word(0.0, 0.5, "Hello"), _word(0.5, 1.2, "world")]
    cue = _cue(0.0, 1.2, "Hello world", words=words)
    out = cues_to_ass([cue], CaptionStyle(animation="pop", karaoke=True))
    dlg = _dialogue(out)
    assert "\\fscx60" in dlg
    assert "{\\k50}Hello" in dlg
    assert "{\\k70}world" in dlg
    # scale prefix must come before the first \k tag
    assert dlg.index("\\fscx60") < dlg.index("{\\k50}")
