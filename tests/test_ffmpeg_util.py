"""Tests for ffmpeg binary resolution (prefer a libass-capable build)."""

import os

from vlogkit.ffmpeg_util import has_libass, resolve_ffmpeg


def test_has_libass_returns_bool():
    assert isinstance(has_libass("ffmpeg"), bool)


def test_resolve_prefers_libass_capable_candidate(tmp_path):
    # Two fake binaries; only the second has libass.
    plain = tmp_path / "ffmpeg_plain"
    full = tmp_path / "ffmpeg_full"
    plain.write_text("#!/bin/sh\n")
    full.write_text("#!/bin/sh\n")
    plain.chmod(0o755)
    full.chmod(0o755)

    libass = {str(full): True, str(plain): False}
    chosen = resolve_ffmpeg(
        preferred=str(plain),
        candidates=[str(full)],
        has_libass_fn=lambda b: libass.get(b, False),
    )
    assert chosen == str(full)


def test_resolve_falls_back_to_existing_when_none_have_libass(tmp_path):
    plain = tmp_path / "ffmpeg_plain"
    plain.write_text("#!/bin/sh\n")
    plain.chmod(0o755)
    chosen = resolve_ffmpeg(
        preferred=str(plain),
        candidates=[],
        has_libass_fn=lambda b: False,
    )
    # No libass anywhere -> return the preferred existing binary so cut/concat still works.
    assert chosen == str(plain)


def test_resolve_falls_back_to_path_ffmpeg_when_preferred_missing():
    import shutil

    chosen = resolve_ffmpeg(
        preferred="/nonexistent/ffmpeg",
        candidates=["/also/missing/ffmpeg"],
        has_libass_fn=lambda b: False,
    )
    # The implicit "ffmpeg" PATH lookup wins when nothing else exists; if PATH
    # has no ffmpeg either, the bare string is returned.
    expected = shutil.which("ffmpeg") or "ffmpeg"
    assert chosen == expected
