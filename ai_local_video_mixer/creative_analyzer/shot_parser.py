from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import ShotAnalysis


@dataclass(slots=True)
class SceneBoundary:
    """Raw scene boundary from the existing video pipeline."""

    start: float
    end: float


class ShotParser:
    """Convert scene boundaries into creative editing roles.

    This first version intentionally does not pretend to understand advertising
    magic. It creates a stable layer where later vision models can add evidence.
    """

    def parse(
        self,
        scenes: Iterable[SceneBoundary | dict],
    ) -> list[ShotAnalysis]:
        shots: list[ShotAnalysis] = []

        for index, scene in enumerate(scenes):
            if isinstance(scene, dict):
                start = float(scene.get("start", 0))
                end = float(scene.get("end", start))
            else:
                start = scene.start
                end = scene.end

            shots.append(
                ShotAnalysis(
                    start=start,
                    end=end,
                    role=self._guess_role(index, start),
                )
            )

        return shots

    @staticmethod
    def _guess_role(index: int, start: float) -> str:
        if index == 0 or start <= 3:
            return "hook"
        return "unknown"
