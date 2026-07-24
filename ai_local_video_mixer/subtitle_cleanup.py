from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Iterable

from .material_intelligence import BoundingBox, ShotIntelligence, TextRegion


@dataclass(slots=True)
class TextCoverPlan:
    text: str
    method: str
    bbox: BoundingBox
    first_frame: int
    last_frame: int
    conflict_score: float
    feather_pixels: int = 10
    blur_radius: int = 12
    darken_alpha: float = 0.12
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text).casefold()


def text_conflict_score(original: str, replacement: str) -> float:
    left = _normalize_text(original)
    right = _normalize_text(replacement)
    if not left:
        return 0.0
    if not right:
        return 1.0
    similarity = SequenceMatcher(a=left, b=right).ratio()
    return round(max(0.0, min(1.0, 1.0 - similarity)), 4)


def _is_bottom_region(box: BoundingBox) -> bool:
    return box.y >= 0.62 and box.height <= 0.30


def _is_small_region(box: BoundingBox) -> bool:
    return box.width * box.height <= 0.18


def choose_cover_method(
    region: TextRegion,
    replacement_text: str,
    subject_overlap: bool = False,
    background_complexity: float = 0.5,
) -> TextCoverPlan | None:
    if region.bbox is None:
        return None
    conflict = text_conflict_score(region.text, replacement_text)
    if conflict < 0.25:
        return None
    box = region.bbox
    complexity = max(0.0, min(1.0, background_complexity))
    if subject_overlap:
        method = "reject_or_reframe"
        reason = "原字幕与主体重叠，自动遮盖会破坏人物或产品"
    elif _is_bottom_region(box) and box.y + box.height >= 0.88:
        method = "crop_or_reframe"
        reason = "字幕贴近底边，优先轻微放大并上移构图"
    elif _is_small_region(box) and complexity <= 0.45:
        method = "blur_patch"
        reason = "区域较小且背景较简单，使用局部羽化模糊"
    elif _is_small_region(box):
        method = "frosted_caption_patch"
        reason = "复杂背景使用局部磨砂承托，不铺大色块"
    else:
        method = "reject_or_reframe"
        reason = "原字幕区域过大，不允许用大面积色块硬盖"
    return TextCoverPlan(
        text=region.text,
        method=method,
        bbox=box,
        first_frame=region.first_frame,
        last_frame=region.last_frame,
        conflict_score=conflict,
        reason=reason,
    )


def plan_subtitle_cleanup(
    analysis: ShotIntelligence,
    replacement_text: str,
    subject_overlap: bool = False,
    background_complexity: float = 0.5,
) -> list[TextCoverPlan]:
    plans: list[TextCoverPlan] = []
    for region in analysis.original_subtitles:
        plan = choose_cover_method(
            region,
            replacement_text=replacement_text,
            subject_overlap=subject_overlap,
            background_complexity=background_complexity,
        )
        if plan is not None:
            plans.append(plan)
    return plans


def _pixel_box(box: BoundingBox, width: int, height: int) -> tuple[int, int, int, int]:
    x = max(0, min(width - 1, round(box.x * width)))
    y = max(0, min(height - 1, round(box.y * height)))
    w = max(2, min(width - x, round(box.width * width)))
    h = max(2, min(height - y, round(box.height * height)))
    return x, y, w, h


def build_blur_patch_filter(
    input_label: str,
    output_label: str,
    plan: TextCoverPlan,
    width: int,
    height: int,
    index: int = 0,
) -> list[str]:
    if plan.method not in {"blur_patch", "frosted_caption_patch"}:
        raise ValueError(f"Cover method cannot be rendered as a patch: {plan.method}")
    x, y, w, h = _pixel_box(plan.bbox, width, height)
    pad = max(2, plan.feather_pixels)
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(width - x, w + pad * 2)
    h = min(height - y, h + pad * 2)
    base = f"cover_base_{index}"
    patch = f"cover_patch_{index}"
    merged = output_label
    filters = [f"[{input_label}]split=2[{base}][cover_src_{index}]"]
    filters.append(
        f"[cover_src_{index}]crop={w}:{h}:{x}:{y},"
        f"boxblur=luma_radius={max(2, plan.blur_radius)}:luma_power=1[{patch}]"
    )
    filters.append(f"[{base}][{patch}]overlay={x}:{y}[cover_overlay_{index}]")
    if plan.method == "frosted_caption_patch":
        filters.append(
            f"[cover_overlay_{index}]drawbox=x={x}:y={y}:w={w}:h={h}:"
            f"color=black@{max(0.0, min(0.35, plan.darken_alpha)):.3f}:t=fill[{merged}]"
        )
    else:
        filters.append(f"[cover_overlay_{index}]null[{merged}]")
    return filters


def summarize_cleanup_risk(plans: Iterable[TextCoverPlan]) -> dict[str, int]:
    result = {
        "crop_or_reframe": 0,
        "blur_patch": 0,
        "frosted_caption_patch": 0,
        "reject_or_reframe": 0,
    }
    for plan in plans:
        result[plan.method] = result.get(plan.method, 0) + 1
    return result
