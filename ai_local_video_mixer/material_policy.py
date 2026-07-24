from __future__ import annotations

from typing import Any

from .material_intelligence import MaterialIntelligenceEngine, ShotIntelligence
from .models import MediaClip


class StrictMaterialIntelligenceEngine(MaterialIntelligenceEngine):
    """Production policy: packaging and uncertain containers fail closed."""

    def _build_analysis(
        self,
        clip_id: str,
        timestamps: list[float],
        payload: dict[str, Any],
    ) -> ShotIntelligence:
        analysis = super()._build_analysis(clip_id, timestamps, payload)
        packaging_objects = [
            item
            for item in analysis.detected_objects
            if item.category in {"retail_packaging", "shipping_packaging"}
        ]
        unknown_objects = [
            item
            for item in analysis.detected_objects
            if item.category == "unknown_container"
        ]
        if packaging_objects:
            analysis.packaging_confidence = max(
                analysis.packaging_confidence,
                max(item.confidence for item in packaging_objects),
            )
            analysis.contains_product_packaging = True
            if analysis.packaging_type == "none":
                analysis.packaging_type = (
                    "shipping_packaging"
                    if any(item.category == "shipping_packaging" for item in packaging_objects)
                    else "retail_packaging"
                )
        if (
            self.config.hard_reject_product_packaging
            and analysis.contains_product_packaging
            and analysis.packaging_confidence >= self.config.packaging_confidence_threshold
            and "product_packaging_detected" not in analysis.reject_reasons
        ):
            analysis.reject_reasons.append("product_packaging_detected")
        if unknown_objects:
            highest_unknown = max(item.confidence for item in unknown_objects)
            if highest_unknown >= self.config.uncertain_object_confidence_threshold:
                analysis.contains_unknown_container = True
        if (
            self.config.hard_reject_unknown_container
            and analysis.contains_unknown_container
            and "unknown_container_detected" not in analysis.reject_reasons
        ):
            analysis.reject_reasons.append("unknown_container_detected")
        analysis.reject_reasons = list(dict.fromkeys(analysis.reject_reasons))
        analysis.usable = not analysis.reject_reasons
        return analysis

    def _apply_to_clip(self, clip: MediaClip, analysis: ShotIntelligence) -> None:
        super()._apply_to_clip(clip, analysis)
        policy_markers = {
            "analysis_failed",
            "hard_reject",
            "product_packaging_detected",
            "shipping_packaging_detected",
            "unknown_container_detected",
            "watermark_detected",
        }
        clip.tags = [item for item in clip.tags if item not in policy_markers]
        clip.tags = list(dict.fromkeys([*clip.tags, *analysis.reject_reasons]))
        clip.usable = analysis.usable
        self.catalog.upsert_clip(clip)
