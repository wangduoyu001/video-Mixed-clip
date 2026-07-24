from __future__ import annotations

import base64
import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import MediaCatalog
from .config import MaterialIntelligenceConfig
from .models import MediaClip
from .ollama_adapter import OllamaClient, OllamaError
from .thumbnails import ThumbnailError, extract_thumbnail


_PACKAGING_TYPES = {
    "none",
    "retail_packaging",
    "shipping_packaging",
    "unknown_container",
}
_OBJECT_CATEGORIES = {
    "product",
    "retail_packaging",
    "shipping_packaging",
    "shooting_prop",
    "background_object",
    "unknown_container",
}


@dataclass(slots=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_value(cls, value: Any) -> BoundingBox | None:
        if not isinstance(value, list) or len(value) != 4:
            return None
        try:
            x, y, width, height = (float(item) for item in value)
        except (TypeError, ValueError):
            return None
        values = [max(0.0, min(1.0, item)) for item in (x, y, width, height)]
        return cls(*values)


@dataclass(slots=True)
class DetectedObject:
    name: str
    category: str
    confidence: float
    evidence_frames: list[int] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    bbox: BoundingBox | None = None


@dataclass(slots=True)
class TextRegion:
    text: str
    kind: str
    confidence: float
    first_frame: int
    last_frame: int
    bbox: BoundingBox | None = None


@dataclass(slots=True)
class ShotIntelligence:
    clip_id: str
    sampled_timestamps: list[float]
    visible_facts: list[str]
    temporal_actions: list[str]
    subjects: list[str]
    scene: str
    detected_objects: list[DetectedObject]
    original_subtitles: list[TextRegion]
    screen_text: list[TextRegion]
    contains_product: bool
    contains_product_packaging: bool
    packaging_type: str
    packaging_confidence: float
    contains_unknown_container: bool
    watermark: bool
    emotions: list[str]
    shot_type: str
    camera_motion: str
    movement_direction: str
    lighting: str
    color_style: str
    composition: str
    narrative_functions: list[str]
    possible_implications: list[str]
    editing_techniques: list[str]
    quality_score: float
    confidence: float
    usable: bool
    reject_reasons: list[str]
    analyzed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MaterialAnalysisSummary:
    requested: int = 0
    analyzed: int = 0
    accepted: int = 0
    rejected: int = 0
    packaging_rejected: int = 0
    uncertain_rejected: int = 0
    watermark_rejected: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS shot_intelligence (
    clip_id TEXT PRIMARY KEY,
    analysis_json TEXT NOT NULL,
    usable INTEGER NOT NULL,
    contains_product_packaging INTEGER NOT NULL,
    packaging_type TEXT NOT NULL,
    packaging_confidence REAL NOT NULL,
    contains_original_subtitles INTEGER NOT NULL,
    reject_reasons_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shot_intelligence_usable
ON shot_intelligence(usable);
CREATE INDEX IF NOT EXISTS idx_shot_intelligence_packaging
ON shot_intelligence(contains_product_packaging, packaging_type);
"""


class MaterialIntelligenceStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(_SCHEMA)

    def upsert(self, analysis: ShotIntelligence) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shot_intelligence(
                    clip_id, analysis_json, usable, contains_product_packaging,
                    packaging_type, packaging_confidence, contains_original_subtitles,
                    reject_reasons_json, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clip_id) DO UPDATE SET
                    analysis_json=excluded.analysis_json,
                    usable=excluded.usable,
                    contains_product_packaging=excluded.contains_product_packaging,
                    packaging_type=excluded.packaging_type,
                    packaging_confidence=excluded.packaging_confidence,
                    contains_original_subtitles=excluded.contains_original_subtitles,
                    reject_reasons_json=excluded.reject_reasons_json,
                    analyzed_at=excluded.analyzed_at
                """,
                (
                    analysis.clip_id,
                    json.dumps(analysis.to_dict(), ensure_ascii=False),
                    int(analysis.usable),
                    int(analysis.contains_product_packaging),
                    analysis.packaging_type,
                    analysis.packaging_confidence,
                    int(bool(analysis.original_subtitles)),
                    json.dumps(analysis.reject_reasons, ensure_ascii=False),
                    analysis.analyzed_at,
                ),
            )

    def get(self, clip_id: str) -> ShotIntelligence | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT analysis_json FROM shot_intelligence WHERE clip_id = ?",
                (clip_id,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(str(row["analysis_json"]))
        return shot_intelligence_from_dict(payload)

    def is_usable(self, clip_id: str) -> bool | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT usable FROM shot_intelligence WHERE clip_id = ?",
                (clip_id,),
            ).fetchone()
        return bool(row["usable"]) if row else None


_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "visible_facts": {"type": "array", "items": {"type": "string"}},
        "temporal_actions": {"type": "array", "items": {"type": "string"}},
        "subjects": {"type": "array", "items": {"type": "string"}},
        "scene": {"type": "string"},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": sorted(_OBJECT_CATEGORIES),
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_frames": {"type": "array", "items": {"type": "integer"}},
                    "text": {"type": "array", "items": {"type": "string"}},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["name", "category", "confidence", "evidence_frames", "text", "bbox"],
            },
        },
        "original_subtitles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "first_frame": {"type": "integer"},
                    "last_frame": {"type": "integer"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["text", "confidence", "first_frame", "last_frame", "bbox"],
            },
        },
        "screen_text": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "first_frame": {"type": "integer"},
                    "last_frame": {"type": "integer"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["text", "kind", "confidence", "first_frame", "last_frame", "bbox"],
            },
        },
        "contains_product": {"type": "boolean"},
        "contains_product_packaging": {"type": "boolean"},
        "packaging_type": {"type": "string", "enum": sorted(_PACKAGING_TYPES)},
        "packaging_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "contains_unknown_container": {"type": "boolean"},
        "watermark": {"type": "boolean"},
        "emotions": {"type": "array", "items": {"type": "string"}},
        "shot_type": {"type": "string"},
        "camera_motion": {"type": "string"},
        "movement_direction": {"type": "string"},
        "lighting": {"type": "string"},
        "color_style": {"type": "string"},
        "composition": {"type": "string"},
        "narrative_functions": {"type": "array", "items": {"type": "string"}},
        "possible_implications": {"type": "array", "items": {"type": "string"}},
        "editing_techniques": {"type": "array", "items": {"type": "string"}},
        "quality_score": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "visible_facts",
        "temporal_actions",
        "subjects",
        "scene",
        "objects",
        "original_subtitles",
        "screen_text",
        "contains_product",
        "contains_product_packaging",
        "packaging_type",
        "packaging_confidence",
        "contains_unknown_container",
        "watermark",
        "emotions",
        "shot_type",
        "camera_motion",
        "movement_direction",
        "lighting",
        "color_style",
        "composition",
        "narrative_functions",
        "possible_implications",
        "editing_techniques",
        "quality_score",
        "confidence",
    ],
}


def _string_list(payload: dict[str, Any], key: str, limit: int = 24) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    result = [str(item).strip() for item in values if str(item).strip()]
    return list(dict.fromkeys(result))[:limit]


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def build_sample_timestamps(
    start: float,
    end: float,
    interval_seconds: float = 0.5,
    minimum_frames: int = 4,
    maximum_frames: int = 12,
) -> list[float]:
    start = max(0.0, float(start))
    end = max(start, float(end))
    duration = end - start
    if duration <= 0.001:
        return [round(start, 3)]
    maximum = max(1, int(maximum_frames))
    minimum = max(1, min(maximum, int(minimum_frames)))
    interval = max(0.1, float(interval_seconds))
    desired = max(minimum, min(maximum, int(duration / interval) + 1))
    if desired == 1:
        return [round(start + duration / 2, 3)]
    edge = min(0.08, duration / 10)
    first = start + edge
    last = max(first, end - edge)
    step = (last - first) / max(1, desired - 1)
    return [round(first + index * step, 3) for index in range(desired)]


def _parse_objects(payload: dict[str, Any]) -> list[DetectedObject]:
    raw_objects = payload.get("objects")
    if not isinstance(raw_objects, list):
        return []
    result: list[DetectedObject] = []
    for raw in raw_objects:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "background_object")
        if category not in _OBJECT_CATEGORIES:
            category = "unknown_container"
        frames = raw.get("evidence_frames")
        result.append(
            DetectedObject(
                name=str(raw.get("name") or "unknown").strip(),
                category=category,
                confidence=_clamp(raw.get("confidence")),
                evidence_frames=[int(item) for item in frames if isinstance(item, int)]
                if isinstance(frames, list)
                else [],
                text=_string_list(raw, "text", limit=16),
                bbox=BoundingBox.from_value(raw.get("bbox")),
            )
        )
    return result


def _parse_text_regions(payload: dict[str, Any], key: str, default_kind: str) -> list[TextRegion]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return []
    result: list[TextRegion] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        result.append(
            TextRegion(
                text=text,
                kind=str(row.get("kind") or default_kind).strip(),
                confidence=_clamp(row.get("confidence")),
                first_frame=max(0, int(row.get("first_frame") or 0)),
                last_frame=max(0, int(row.get("last_frame") or 0)),
                bbox=BoundingBox.from_value(row.get("bbox")),
            )
        )
    return result


def shot_intelligence_from_dict(payload: dict[str, Any]) -> ShotIntelligence:
    return ShotIntelligence(
        clip_id=str(payload["clip_id"]),
        sampled_timestamps=[float(item) for item in payload.get("sampled_timestamps", [])],
        visible_facts=[str(item) for item in payload.get("visible_facts", [])],
        temporal_actions=[str(item) for item in payload.get("temporal_actions", [])],
        subjects=[str(item) for item in payload.get("subjects", [])],
        scene=str(payload.get("scene") or ""),
        detected_objects=[
            DetectedObject(
                name=str(item.get("name") or "unknown"),
                category=str(item.get("category") or "background_object"),
                confidence=float(item.get("confidence") or 0.0),
                evidence_frames=[int(value) for value in item.get("evidence_frames", [])],
                text=[str(value) for value in item.get("text", [])],
                bbox=BoundingBox(**item["bbox"]) if isinstance(item.get("bbox"), dict) else None,
            )
            for item in payload.get("detected_objects", [])
            if isinstance(item, dict)
        ],
        original_subtitles=[
            TextRegion(
                text=str(item.get("text") or ""),
                kind=str(item.get("kind") or "subtitle"),
                confidence=float(item.get("confidence") or 0.0),
                first_frame=int(item.get("first_frame") or 0),
                last_frame=int(item.get("last_frame") or 0),
                bbox=BoundingBox(**item["bbox"]) if isinstance(item.get("bbox"), dict) else None,
            )
            for item in payload.get("original_subtitles", [])
            if isinstance(item, dict)
        ],
        screen_text=[
            TextRegion(
                text=str(item.get("text") or ""),
                kind=str(item.get("kind") or "screen_text"),
                confidence=float(item.get("confidence") or 0.0),
                first_frame=int(item.get("first_frame") or 0),
                last_frame=int(item.get("last_frame") or 0),
                bbox=BoundingBox(**item["bbox"]) if isinstance(item.get("bbox"), dict) else None,
            )
            for item in payload.get("screen_text", [])
            if isinstance(item, dict)
        ],
        contains_product=bool(payload.get("contains_product")),
        contains_product_packaging=bool(payload.get("contains_product_packaging")),
        packaging_type=str(payload.get("packaging_type") or "none"),
        packaging_confidence=float(payload.get("packaging_confidence") or 0.0),
        contains_unknown_container=bool(payload.get("contains_unknown_container")),
        watermark=bool(payload.get("watermark")),
        emotions=[str(item) for item in payload.get("emotions", [])],
        shot_type=str(payload.get("shot_type") or "unknown"),
        camera_motion=str(payload.get("camera_motion") or "unknown"),
        movement_direction=str(payload.get("movement_direction") or "unknown"),
        lighting=str(payload.get("lighting") or ""),
        color_style=str(payload.get("color_style") or ""),
        composition=str(payload.get("composition") or ""),
        narrative_functions=[str(item) for item in payload.get("narrative_functions", [])],
        possible_implications=[str(item) for item in payload.get("possible_implications", [])],
        editing_techniques=[str(item) for item in payload.get("editing_techniques", [])],
        quality_score=float(payload.get("quality_score") or 0.0),
        confidence=float(payload.get("confidence") or 0.0),
        usable=bool(payload.get("usable")),
        reject_reasons=[str(item) for item in payload.get("reject_reasons", [])],
        analyzed_at=str(payload.get("analyzed_at") or ""),
    )


class MaterialVisionAnalyzer:
    def __init__(self, client: OllamaClient, model: str):
        self.client = client
        self.model = model

    def analyze(self, frame_paths: list[Path], timestamps: list[float]) -> dict[str, Any]:
        if not frame_paths:
            raise ValueError("No analysis frames were supplied")
        images = [base64.b64encode(path.read_bytes()).decode("ascii") for path in frame_paths]
        timestamp_text = ", ".join(
            f"frame {index}={timestamp:.3f}s" for index, timestamp in enumerate(timestamps)
        )
        prompt = (
            "你正在分析同一个视频镜头按时间顺序抽取的多帧画面。"
            "必须综合所有帧，不得只看第一帧。\n"
            f"帧时间：{timestamp_text}\n"
            "任务：识别客观画面事实、动作变化、人物、场景、景别、运镜、运动方向、"
            "光线、色彩、构图、原视频字幕、屏幕文字、水印、叙事功能、可能暗示和剪辑表现手法。\n"
            "最重要规则：精准区分产品本体、产品零售包装、运输包装、拍摄道具、普通背景物和无法确认的容器。"
            "产品包装包括带品牌、商品名、规格、条码、成分、标签、塑封、瓶贴、盒袋包装，"
            "以及人物正在开箱、拆袋、展示包装的情况。拍摄道具只是布景物件，不能因为外形像瓶盒就草率认定。"
            "只要任意帧出现产品包装，contains_product_packaging必须为true，并给出证据帧。"
            "无法确认是道具还是包装的瓶、盒、袋应标为unknown_container，不要乐观放行。\n"
            "original_subtitles只记录叠加在视频上的字幕；screen_text记录界面、招牌、包装或场景文字。"
            "bbox统一使用0到1归一化坐标[x,y,width,height]。"
            "possible_implications必须与可见证据一致，不能编造产品功效或人物身份。"
        )
        return self.client.generate(
            model=self.model,
            prompt=prompt,
            schema=_ANALYSIS_SCHEMA,
            images=images,
            system="只输出严格符合JSON Schema的多帧素材分析结果。包装判断宁可保守，不得漏放疑似包装。",
            timeout=max(self.client.timeout, 300.0),
        )


class MaterialIntelligenceEngine:
    def __init__(
        self,
        catalog: MediaCatalog,
        store: MaterialIntelligenceStore,
        analyzer: MaterialVisionAnalyzer,
        ffmpeg_path: str | None,
        config: MaterialIntelligenceConfig,
    ):
        self.catalog = catalog
        self.store = store
        self.analyzer = analyzer
        self.ffmpeg_path = ffmpeg_path
        self.config = config

    def analyze_catalog(
        self,
        limit: int | None = None,
        force: bool = False,
    ) -> MaterialAnalysisSummary:
        clips = self.catalog.list_clips(usable_only=False)
        if limit is not None:
            clips = clips[: max(0, limit)]
        summary = MaterialAnalysisSummary(requested=len(clips))
        for clip in clips:
            if not force and self.store.get(clip.clip_id) is not None:
                continue
            try:
                analysis = self.analyze_clip(clip)
            except (OllamaError, ThumbnailError, FileNotFoundError, OSError, ValueError) as exc:
                summary.failed += 1
                summary.errors.append(f"{clip.clip_id}: {exc}")
                if self.config.fail_closed_on_analysis_error:
                    clip.usable = False
                    clip.tags = list(dict.fromkeys([*clip.tags, "analysis_failed", "hard_reject"]))
                    self.catalog.upsert_clip(clip)
                continue
            self.store.upsert(analysis)
            self._apply_to_clip(clip, analysis)
            summary.analyzed += 1
            if analysis.usable:
                summary.accepted += 1
            else:
                summary.rejected += 1
            if "product_packaging_detected" in analysis.reject_reasons:
                summary.packaging_rejected += 1
            if "unknown_container_detected" in analysis.reject_reasons:
                summary.uncertain_rejected += 1
            if "watermark_detected" in analysis.reject_reasons:
                summary.watermark_rejected += 1
        return summary

    def analyze_clip(self, clip: MediaClip) -> ShotIntelligence:
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg is required for multi-frame material analysis")
        source = Path(clip.source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Media file not found: {source}")
        timestamps = build_sample_timestamps(
            clip.source_start,
            clip.source_end,
            interval_seconds=self.config.frame_interval_seconds,
            minimum_frames=self.config.minimum_frames,
            maximum_frames=self.config.maximum_frames,
        )
        frame_root = Path(self.config.analysis_root) / "frames" / clip.clip_id
        frame_root.mkdir(parents=True, exist_ok=True)
        frames: list[Path] = []
        try:
            for index, timestamp in enumerate(timestamps):
                frames.append(
                    extract_thumbnail(
                        source_path=source,
                        timestamp=timestamp,
                        output_path=frame_root / f"{index:03d}_{timestamp:.3f}.jpg",
                        ffmpeg_path=self.ffmpeg_path,
                        width=self.config.frame_width,
                    )
                )
            payload = self.analyzer.analyze(frames, timestamps)
            return self._build_analysis(clip.clip_id, timestamps, payload)
        finally:
            if not self.config.keep_analysis_frames:
                shutil.rmtree(frame_root, ignore_errors=True)

    def _build_analysis(
        self,
        clip_id: str,
        timestamps: list[float],
        payload: dict[str, Any],
    ) -> ShotIntelligence:
        objects = _parse_objects(payload)
        original_subtitles = _parse_text_regions(payload, "original_subtitles", "subtitle")
        screen_text = _parse_text_regions(payload, "screen_text", "screen_text")
        packaging_type = str(payload.get("packaging_type") or "none")
        if packaging_type not in _PACKAGING_TYPES:
            packaging_type = "unknown_container"
        packaging_confidence = _clamp(payload.get("packaging_confidence"))
        packaging_objects = [
            item
            for item in objects
            if item.category in {"retail_packaging", "shipping_packaging"}
            and item.confidence >= self.config.packaging_confidence_threshold
        ]
        unknown_objects = [
            item
            for item in objects
            if item.category == "unknown_container"
            and item.confidence >= self.config.uncertain_object_confidence_threshold
        ]
        contains_packaging = bool(payload.get("contains_product_packaging")) or bool(packaging_objects)
        contains_unknown = bool(payload.get("contains_unknown_container")) or bool(unknown_objects)
        watermark = bool(payload.get("watermark"))
        reject_reasons: list[str] = []
        if (
            self.config.hard_reject_product_packaging
            and contains_packaging
            and packaging_confidence >= self.config.packaging_confidence_threshold
        ):
            reject_reasons.append("product_packaging_detected")
        if (
            self.config.hard_reject_shipping_packaging
            and packaging_type == "shipping_packaging"
        ):
            reject_reasons.append("shipping_packaging_detected")
        if self.config.hard_reject_unknown_container and contains_unknown:
            reject_reasons.append("unknown_container_detected")
        if self.config.hard_reject_watermark and watermark:
            reject_reasons.append("watermark_detected")
        return ShotIntelligence(
            clip_id=clip_id,
            sampled_timestamps=timestamps,
            visible_facts=_string_list(payload, "visible_facts"),
            temporal_actions=_string_list(payload, "temporal_actions"),
            subjects=_string_list(payload, "subjects"),
            scene=str(payload.get("scene") or "").strip(),
            detected_objects=objects,
            original_subtitles=original_subtitles,
            screen_text=screen_text,
            contains_product=bool(payload.get("contains_product")),
            contains_product_packaging=contains_packaging,
            packaging_type=packaging_type,
            packaging_confidence=packaging_confidence,
            contains_unknown_container=contains_unknown,
            watermark=watermark,
            emotions=_string_list(payload, "emotions", limit=8),
            shot_type=str(payload.get("shot_type") or "unknown").strip(),
            camera_motion=str(payload.get("camera_motion") or "unknown").strip(),
            movement_direction=str(payload.get("movement_direction") or "unknown").strip(),
            lighting=str(payload.get("lighting") or "").strip(),
            color_style=str(payload.get("color_style") or "").strip(),
            composition=str(payload.get("composition") or "").strip(),
            narrative_functions=_string_list(payload, "narrative_functions"),
            possible_implications=_string_list(payload, "possible_implications"),
            editing_techniques=_string_list(payload, "editing_techniques"),
            quality_score=_clamp(payload.get("quality_score"), default=0.5),
            confidence=_clamp(payload.get("confidence"), default=0.5),
            usable=not reject_reasons,
            reject_reasons=list(dict.fromkeys(reject_reasons)),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_to_clip(self, clip: MediaClip, analysis: ShotIntelligence) -> None:
        object_tags = [
            f"object:{item.category}:{item.name}"
            for item in analysis.detected_objects
            if item.name
        ]
        policy_tags = [
            f"packaging:{analysis.packaging_type}",
            "contains_original_subtitles" if analysis.original_subtitles else "no_original_subtitles",
            "contains_product" if analysis.contains_product else "no_product",
        ]
        clip.tags = list(
            dict.fromkeys(
                [
                    *clip.tags,
                    *analysis.subjects,
                    analysis.scene,
                    *analysis.temporal_actions,
                    *analysis.narrative_functions,
                    *analysis.editing_techniques,
                    *object_tags,
                    *policy_tags,
                    *analysis.reject_reasons,
                ]
            )
        )[:64]
        if analysis.visible_facts:
            clip.description = "；".join(analysis.visible_facts[:6])
        clip.emotions = analysis.emotions
        clip.shot_type = analysis.shot_type or clip.shot_type
        clip.camera_motion = analysis.camera_motion or clip.camera_motion
        clip.has_watermark = analysis.watermark
        clip.quality_score = round(
            max(0.0, min(1.0, clip.quality_score * 0.35 + analysis.quality_score * 0.65)),
            4,
        )
        clip.usable = clip.usable and analysis.usable
        self.catalog.upsert_clip(clip)
