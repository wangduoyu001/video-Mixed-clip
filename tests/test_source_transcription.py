from __future__ import annotations

from ai_local_video_mixer.models import MediaClip
from ai_local_video_mixer.source_transcription import transcript_text_for_clip
from ai_local_video_mixer.transcription import TranscriptSegment, TranscriptionResult


def _clip(start: float, end: float) -> MediaClip:
    return MediaClip(
        clip_id="CLP",
        source_id="SRC",
        source_path="source.mp4",
        source_start=start,
        source_end=end,
        duration=end - start,
    )


def test_dialogue_is_attached_only_to_overlapping_clip() -> None:
    result = TranscriptionResult(
        audio_path="source.mp4",
        model="test",
        language="zh",
        duration=10.0,
        text="第一句 第二句",
        segments=[
            TranscriptSegment(segment_id=1, text="第一句", start=0.0, end=2.0),
            TranscriptSegment(segment_id=2, text="第二句", start=5.0, end=7.0),
        ],
    )
    assert transcript_text_for_clip(result, _clip(0.5, 2.5)) == "第一句"
    assert transcript_text_for_clip(result, _clip(4.5, 7.5)) == "第二句"
    assert transcript_text_for_clip(result, _clip(2.5, 4.0)) == ""


def test_short_boundary_touch_is_not_mistaken_for_dialogue() -> None:
    result = TranscriptionResult(
        audio_path="source.mp4",
        model="test",
        language="zh",
        duration=2.0,
        text="边界",
        segments=[TranscriptSegment(segment_id=1, text="边界", start=0.0, end=1.0)],
    )
    assert transcript_text_for_clip(result, _clip(1.0, 2.0)) == ""
