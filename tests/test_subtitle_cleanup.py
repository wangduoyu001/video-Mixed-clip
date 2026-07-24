from __future__ import annotations

from ai_local_video_mixer.material_intelligence import BoundingBox, TextRegion
from ai_local_video_mixer.subtitle_cleanup import (
    build_blur_patch_filter,
    choose_cover_method,
    text_conflict_score,
)


def _region(box: BoundingBox, text: str = "旧字幕") -> TextRegion:
    return TextRegion(
        text=text,
        kind="subtitle",
        confidence=0.95,
        first_frame=0,
        last_frame=5,
        bbox=box,
    )


def test_same_caption_does_not_need_cover() -> None:
    assert text_conflict_score("自动识别素材", "自动识别素材") == 0.0
    plan = choose_cover_method(
        _region(BoundingBox(0.1, 0.8, 0.8, 0.1), text="自动识别素材"),
        replacement_text="自动识别素材",
    )
    assert plan is None


def test_bottom_subtitle_prefers_reframe() -> None:
    plan = choose_cover_method(
        _region(BoundingBox(0.1, 0.9, 0.8, 0.08)),
        replacement_text="新字幕",
    )
    assert plan is not None
    assert plan.method == "crop_or_reframe"


def test_small_simple_region_uses_local_blur() -> None:
    plan = choose_cover_method(
        _region(BoundingBox(0.2, 0.65, 0.35, 0.1)),
        replacement_text="新字幕",
        background_complexity=0.2,
    )
    assert plan is not None
    assert plan.method == "blur_patch"
    filters = build_blur_patch_filter("in", "out", plan, width=1080, height=1920)
    assert any("boxblur" in item for item in filters)
    assert not any("color=black@1" in item for item in filters)


def test_large_subtitle_region_is_not_hidden_with_big_block() -> None:
    plan = choose_cover_method(
        _region(BoundingBox(0.05, 0.45, 0.9, 0.4)),
        replacement_text="新字幕",
        background_complexity=0.8,
    )
    assert plan is not None
    assert plan.method == "reject_or_reframe"


def test_subject_overlap_rejects_automatic_cover() -> None:
    plan = choose_cover_method(
        _region(BoundingBox(0.2, 0.5, 0.4, 0.15)),
        replacement_text="新字幕",
        subject_overlap=True,
    )
    assert plan is not None
    assert plan.method == "reject_or_reframe"
