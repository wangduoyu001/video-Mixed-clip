from __future__ import annotations

from typing import Iterable

from .schema import SubtitleRegion


class SubtitleAnalyzer:
    """Subtitle analysis foundation.

    OCR engines can provide text boxes later. This layer normalizes their output
    and prepares masking information for replacement copy workflows.
    """

    def analyze(self, ocr_items: Iterable[dict]) -> list[SubtitleRegion]:
        result: list[SubtitleRegion] = []

        for item in ocr_items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            result.append(
                SubtitleRegion(
                    text=text,
                    x=int(item.get("x", 0)),
                    y=int(item.get("y", 0)),
                    width=int(item.get("width", 0)),
                    height=int(item.get("height", 0)),
                )
            )

        return result
