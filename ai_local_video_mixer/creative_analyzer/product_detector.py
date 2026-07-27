from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import ProductAppearance


@dataclass(slots=True)
class DetectionCandidate:
    label: str
    confidence: float
    start: float
    end: float


class ProductDetector:
    """Normalize product detection results from vision models.

    The actual detector can be swapped between local models and APIs without
    changing the creative analysis pipeline.
    """

    def parse(self, candidates: Iterable[dict]) -> list[ProductAppearance]:
        result: list[ProductAppearance] = []

        for item in candidates:
            result.append(
                ProductAppearance(
                    timestamp_start=float(item.get("start", 0)),
                    timestamp_end=float(item.get("end", 0)),
                    product_type=str(item.get("type", "unknown")),
                    confidence=float(item.get("confidence", 0)),
                )
            )

        return result
