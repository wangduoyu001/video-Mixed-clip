from __future__ import annotations

from ai_local_video_mixer.config import MaterialIntelligenceConfig
from ai_local_video_mixer.material_intelligence import (
    MaterialIntelligenceStore,
    build_sample_timestamps,
)
from ai_local_video_mixer.material_policy import StrictMaterialIntelligenceEngine


def _payload(objects: list[dict], **overrides):
    payload = {
        "visible_facts": ["人物把一个物体放到桌面"],
        "temporal_actions": ["手从画外进入", "物体被放到桌上"],
        "subjects": ["人物", "桌面"],
        "scene": "室内拍摄台",
        "objects": objects,
        "original_subtitles": [],
        "screen_text": [],
        "contains_product": True,
        "contains_product_packaging": False,
        "packaging_type": "none",
        "packaging_confidence": 0.1,
        "contains_unknown_container": False,
        "watermark": False,
        "emotions": ["中性"],
        "shot_type": "近景",
        "camera_motion": "固定",
        "movement_direction": "画外到画内",
        "lighting": "柔光",
        "color_style": "自然",
        "composition": "居中",
        "narrative_functions": ["产品展示"],
        "possible_implications": ["展示使用过程"],
        "editing_techniques": ["动作匹配"],
        "quality_score": 0.8,
        "confidence": 0.85,
    }
    payload.update(overrides)
    return payload


def _engine() -> StrictMaterialIntelligenceEngine:
    return StrictMaterialIntelligenceEngine(
        catalog=None,  # type: ignore[arg-type]
        store=None,  # type: ignore[arg-type]
        analyzer=None,  # type: ignore[arg-type]
        ffmpeg_path=None,
        config=MaterialIntelligenceConfig(),
    )


def test_sample_timestamps_cover_full_clip() -> None:
    timestamps = build_sample_timestamps(10.0, 16.0, interval_seconds=0.5, maximum_frames=12)
    assert len(timestamps) == 12
    assert timestamps[0] >= 10.0
    assert timestamps[-1] <= 16.0
    assert timestamps == sorted(timestamps)


def test_high_confidence_packaging_object_is_hard_rejected() -> None:
    analysis = _engine()._build_analysis(
        "CLP_1",
        [0.1, 0.5, 0.9],
        _payload(
            [
                {
                    "name": "带商品名和规格的盒子",
                    "category": "retail_packaging",
                    "confidence": 0.96,
                    "evidence_frames": [1, 2],
                    "text": ["商品名", "30ml"],
                    "bbox": [0.3, 0.3, 0.25, 0.35],
                }
            ]
        ),
    )
    assert analysis.contains_product_packaging is True
    assert analysis.packaging_confidence == 0.96
    assert analysis.usable is False
    assert "product_packaging_detected" in analysis.reject_reasons


def test_unknown_container_fails_closed() -> None:
    analysis = _engine()._build_analysis(
        "CLP_2",
        [0.1, 0.5],
        _payload(
            [
                {
                    "name": "无法确认用途的瓶子",
                    "category": "unknown_container",
                    "confidence": 0.72,
                    "evidence_frames": [0, 1],
                    "text": [],
                    "bbox": [0.2, 0.2, 0.2, 0.4],
                }
            ]
        ),
    )
    assert analysis.contains_unknown_container is True
    assert analysis.usable is False
    assert "unknown_container_detected" in analysis.reject_reasons


def test_shooting_prop_is_not_treated_as_packaging() -> None:
    analysis = _engine()._build_analysis(
        "CLP_3",
        [0.1, 0.5],
        _payload(
            [
                {
                    "name": "无文字木质装饰盒",
                    "category": "shooting_prop",
                    "confidence": 0.91,
                    "evidence_frames": [0, 1],
                    "text": [],
                    "bbox": [0.2, 0.2, 0.2, 0.2],
                }
            ],
            contains_product=False,
        ),
    )
    assert analysis.contains_product_packaging is False
    assert analysis.usable is True


def test_material_store_round_trip(tmp_path) -> None:
    store = MaterialIntelligenceStore(tmp_path / "media.db")
    analysis = _engine()._build_analysis(
        "CLP_4",
        [0.1, 0.5],
        _payload([], contains_product=False),
    )
    store.upsert(analysis)
    loaded = store.get("CLP_4")
    assert loaded is not None
    assert loaded.clip_id == "CLP_4"
    assert store.is_usable("CLP_4") is True
