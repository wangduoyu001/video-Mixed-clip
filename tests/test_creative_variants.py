from __future__ import annotations

import json
from pathlib import Path

from ai_local_video_mixer.config import CreativeVariantConfig
from ai_local_video_mixer.creative_variants import CreativeVariantGenerator


def _clip(clip_id: str, source_id: str, start: float = 0.0) -> dict:
    return {
        "clip_id": clip_id,
        "source_id": source_id,
        "source_path": f"{source_id}.mp4",
        "source_start": start,
        "source_end": start + 3.0,
        "duration": 3.0,
        "description": "可用替换画面",
        "tags": ["测试"],
        "emotions": ["中性"],
        "shot_type": "中景",
        "camera_motion": "固定",
        "width": 1080,
        "height": 1920,
        "quality_score": 0.8,
        "has_watermark": False,
        "usable": True,
        "thumbnail_path": "",
        "has_audio": False,
    }


def _candidate(clip_id: str, source_id: str, score: float) -> dict:
    return {
        "clip": _clip(clip_id, source_id),
        "score": score,
        "reasons": ["semantic=0.8"],
    }


def _write_project(root: Path) -> None:
    timeline = {
        "project_id": "BASE001",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 6.0,
        "segments": [
            {
                "segment_id": "S001",
                "unit_id": "U001",
                "timeline_start": 0.0,
                "timeline_end": 2.0,
                "source_id": "SRC_HOOK",
                "source_path": "hook.mp4",
                "source_start": 0.0,
                "source_end": 2.0,
                "match_score": 0.9,
                "clip_id": "CLIP_HOOK",
            },
            {
                "segment_id": "S002",
                "unit_id": "U002",
                "timeline_start": 2.0,
                "timeline_end": 4.0,
                "source_id": "SRC_BODY_A",
                "source_path": "body_a.mp4",
                "source_start": 0.0,
                "source_end": 2.0,
                "match_score": 0.8,
                "clip_id": "CLIP_BODY_A",
            },
            {
                "segment_id": "S003",
                "unit_id": "U003",
                "timeline_start": 4.0,
                "timeline_end": 6.0,
                "source_id": "SRC_BODY_B",
                "source_path": "body_b.mp4",
                "source_start": 0.0,
                "source_end": 2.0,
                "match_score": 0.8,
                "clip_id": "CLIP_BODY_B",
            },
        ],
        "audio": {},
        "warnings": [],
    }
    candidates = {
        "U001": [_candidate("CLIP_HOOK", "SRC_HOOK", 0.9)],
        "U002": [
            _candidate("CLIP_BODY_A", "SRC_BODY_A", 0.9),
            _candidate("CLIP_U2_ALT1", "SRC_U2_ALT1", 0.85),
            _candidate("CLIP_U2_ALT2", "SRC_U2_ALT2", 0.82),
        ],
        "U003": [
            _candidate("CLIP_BODY_B", "SRC_BODY_B", 0.9),
            _candidate("CLIP_U3_ALT1", "SRC_U3_ALT1", 0.86),
            _candidate("CLIP_U3_ALT2", "SRC_U3_ALT2", 0.81),
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_same_hook_new_body_preserves_hook_and_changes_body(tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    generator = CreativeVariantGenerator(
        project_dir=project,
        config=CreativeVariantConfig(default_variant_count=2),
        material_store=None,
    )
    summary = generator.generate(
        count=2,
        mode="same_hook_new_body",
        hook_seconds=2.0,
        seed=7,
        creative_family_id="CF_TEST",
    )
    assert summary.generated == 2
    timelines = []
    for path in summary.output_paths:
        timeline = json.loads((Path(path) / "timeline.json").read_text(encoding="utf-8"))
        timelines.append(timeline)
        assert timeline["segments"][0]["clip_id"] == "CLIP_HOOK"
        assert timeline["segments"][1]["clip_id"] != "CLIP_BODY_A"
        assert timeline["segments"][2]["clip_id"] != "CLIP_BODY_B"
    assert timelines[0]["segments"][1]["clip_id"] != timelines[1]["segments"][1]["clip_id"]


def test_same_script_new_visuals_can_replace_hook(tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    candidates = json.loads((project / "candidates.json").read_text(encoding="utf-8"))
    candidates["U001"].append(_candidate("CLIP_HOOK_ALT", "SRC_HOOK_ALT", 0.88))
    (project / "candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    generator = CreativeVariantGenerator(
        project_dir=project,
        config=CreativeVariantConfig(default_variant_count=1),
        material_store=None,
    )
    summary = generator.generate(
        count=1,
        mode="same_script_new_visuals",
        seed=11,
        creative_family_id="CF_ALL",
    )
    timeline = json.loads(
        (Path(summary.output_paths[0]) / "timeline.json").read_text(encoding="utf-8")
    )
    assert timeline["segments"][0]["clip_id"] == "CLIP_HOOK_ALT"
