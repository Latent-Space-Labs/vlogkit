"""Transcription via faster-whisper with optional stable-ts alignment."""

from __future__ import annotations

from pathlib import Path

from ..models import TranscriptSegment, WordTimestamp


def transcribe_clip(
    clip_path: Path,
    model_size: str = "base",
    device: str = "auto",
) -> list[TranscriptSegment]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device)
    segments_iter, _info = model.transcribe(
        str(clip_path),
        word_timestamps=True,
        vad_filter=True,
    )

    result: list[TranscriptSegment] = []
    for seg in segments_iter:
        words = []
        if seg.words:
            words = [
                WordTimestamp(
                    start=w.start,
                    end=w.end,
                    word=w.word,
                    confidence=w.probability,
                )
                for w in seg.words
            ]
        result.append(TranscriptSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text.strip(),
            confidence=seg.avg_logprob,
            words=words,
        ))
    return result
