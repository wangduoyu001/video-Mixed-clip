from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(slots=True)
class SubtitleRegion:
    text: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    maskable: bool = True


@dataclass(slots=True)
class ShotAnalysis:
    start: float
    end: float
    role: str = "unknown"
    scene: str = "unknown"
    emotion: str = "unknown"
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProductAppearance:
    timestamp_start: float
    timestamp_end: float
    product_type: str = "unknown"
    confidence: float = 0.0


@dataclass(slots=True)
class CreativeAnalysis:
    video_id: str
    shots: list[ShotAnalysis] = field(default_factory=list)
    subtitles: list[SubtitleRegion] = field(default_factory=list)
    products: list[ProductAppearance] = field(default_factory=list)
    copy_structure: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
