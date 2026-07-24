from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CreativeVariantConfig
from .material_intelligence import MaterialIntelligenceStore
from .models import CandidateClip, Timeline, TimelineSegment
from .review import load_candidates, load_timeline
from .subtitle_cleanup import plan_subtitle_cleanup, summarize_cleanup_risk


@dataclass(slots=True)
class VariantChange:
    segment_id: str
    unit_id: str
    old_clip_id: str
    new_clip_id: str
    old_source_id: str
    new_source_id: str
    candidate_rank: int
    score: float


@dataclass(slots=True)
class CreativeVariantManifest:
    creative_family_id: str
    parent_creative_id: str
    variant_id: str
    mode: str
    test_hypothesis: str
    locked_hook: bool
    locked_cta: bool
    hook_seconds: float
    changed_dimensions: list[str]
    changes: list[VariantChange]
    subtitle_cleanup: dict[str, list[dict[str, Any]]]
    subtitle_cleanup_risk: dict[str, int]
    generated_at: str
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VariantBatchSummary:
    creative_family_id: str
    parent_creative_id: str
    generated: int = 0
    skipped_segments: int = 0
    output_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _candidate_safe(
    candidate: CandidateClip,
    material_store: MaterialIntelligenceStore | None,
    minimum_score: float,
) -> bool:
    clip = candidate.clip
    if not clip.usable or clip.has_watermark or candidate.score < minimum_score:
        return False
    if material_store is not None:
        decision = material_store.is_usable(clip.clip_id)
        if decision is False:
            return False
    return True


def _candidate_pool(
    candidates: list[CandidateClip],
    current: TimelineSegment,
    material_store: MaterialIntelligenceStore | None,
    config: CreativeVariantConfig,
) -> list[tuple[int, CandidateClip]]:
    pool: list[tuple[int, CandidateClip]] = []
    for rank, candidate in enumerate(candidates, start=1):
        if candidate.clip.clip_id == current.clip_id:
            continue
        if not _candidate_safe(candidate, material_store, config.minimum_candidate_score):
            continue
        if candidate.clip.duration + 0.001 < current.duration:
            continue
        pool.append((rank, candidate))
    return pool


def _replace_segment(
    segment: TimelineSegment,
    candidate: CandidateClip,
    rank: int,
) -> VariantChange:
    clip = candidate.clip
    old_clip_id = segment.clip_id
    old_source_id = segment.source_id
    duration = segment.duration
    source_duration = min(duration, clip.duration)
    segment.clip_id = clip.clip_id
    segment.source_id = clip.source_id
    segment.source_path = clip.source_path
    segment.source_start = clip.source_start
    segment.source_end = round(clip.source_start + source_duration, 3)
    segment.match_score = candidate.score
    segment.match_reasons = [*candidate.reasons, "creative_variant_replacement"]
    segment.candidate_rank = rank
    segment.audio_enabled = clip.has_audio
    segment.speed = max(0.5, min(2.0, round(source_duration / max(duration, 0.001), 4)))
    segment.locked = False
    segment.review_status = "variant_generated"
    segment.replacement_reason = "creative_variant"
    return VariantChange(
        segment_id=segment.segment_id,
        unit_id=segment.unit_id,
        old_clip_id=old_clip_id,
        new_clip_id=clip.clip_id,
        old_source_id=old_source_id,
        new_source_id=clip.source_id,
        candidate_rank=rank,
        score=candidate.score,
    )


class CreativeVariantGenerator:
    def __init__(
        self,
        project_dir: str | Path,
        config: CreativeVariantConfig,
        material_store: MaterialIntelligenceStore | None = None,
    ):
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.config = config
        self.material_store = material_store
        self.parent_timeline = load_timeline(self.project_dir)
        self.candidates = load_candidates(self.project_dir)
        self.position_history: dict[str, set[str]] = {}

    def generate(
        self,
        count: int | None = None,
        mode: str = "same_hook_new_body",
        hook_seconds: float | None = None,
        preserve_cta: bool | None = None,
        seed: int = 0,
        creative_family_id: str | None = None,
    ) -> VariantBatchSummary:
        supported = {"same_hook_new_body", "same_script_new_visuals"}
        if mode not in supported:
            raise ValueError(f"Unsupported variant mode: {mode}")
        total = max(1, count or self.config.default_variant_count)
        hook_limit = max(0.0, hook_seconds if hook_seconds is not None else self.config.hook_seconds)
        keep_cta = (
            self.config.preserve_cta_by_default if preserve_cta is None else preserve_cta
        )
        family_id = creative_family_id or (
            f"CF_{self.parent_timeline.project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        summary = VariantBatchSummary(
            creative_family_id=family_id,
            parent_creative_id=self.parent_timeline.project_id,
        )
        output_root = self.project_dir / self.config.output_dir_name / family_id
        batch_random = random.Random(seed)
        for variant_index in range(1, total + 1):
            variant_seed = batch_random.randint(0, 2**31 - 1)
            timeline, manifest, skipped = self._generate_one(
                family_id=family_id,
                variant_index=variant_index,
                mode=mode,
                hook_seconds=hook_limit,
                preserve_cta=keep_cta,
                seed=variant_seed,
            )
            target = output_root / manifest.variant_id
            _atomic_write_json(target / "timeline.json", timeline.to_dict())
            _atomic_write_json(target / "variant_manifest.json", manifest.to_dict())
            summary.generated += 1
            summary.skipped_segments += skipped
            summary.output_paths.append(str(target))
        _atomic_write_json(output_root / "batch_summary.json", summary.to_dict())
        return summary

    def _generate_one(
        self,
        family_id: str,
        variant_index: int,
        mode: str,
        hook_seconds: float,
        preserve_cta: bool,
        seed: int,
    ) -> tuple[Timeline, CreativeVariantManifest, int]:
        timeline = copy.deepcopy(self.parent_timeline)
        rng = random.Random(seed)
        variant_id = f"V{variant_index:03d}"
        used_clip_ids = {segment.clip_id for segment in timeline.segments if segment.clip_id}
        changes: list[VariantChange] = []
        cleanup: dict[str, list[dict[str, Any]]] = {}
        cleanup_plans = []
        skipped = 0
        for index, segment in enumerate(timeline.segments):
            is_hook = segment.timeline_start < hook_seconds
            is_cta = preserve_cta and index == len(timeline.segments) - 1
            if mode == "same_hook_new_body" and is_hook:
                segment.locked = True
                segment.review_status = "inherited_hook"
                continue
            if is_cta:
                segment.locked = True
                segment.review_status = "inherited_cta"
                continue
            pool = _candidate_pool(
                self.candidates.get(segment.unit_id, []),
                segment,
                material_store=self.material_store,
                config=self.config,
            )
            if not pool:
                skipped += 1
                continue
            history = self.position_history.setdefault(segment.segment_id, set())
            filtered = [
                item
                for item in pool
                if item[1].clip.clip_id not in used_clip_ids
                and (
                    not self.config.avoid_same_clip_position_across_variants
                    or item[1].clip.clip_id not in history
                )
            ]
            if not filtered:
                filtered = [item for item in pool if item[1].clip.clip_id not in used_clip_ids]
            if not filtered:
                filtered = pool
            if self.config.avoid_repeating_source_in_adjacent_segments:
                previous_source = timeline.segments[index - 1].source_id if index > 0 else ""
                next_source = (
                    timeline.segments[index + 1].source_id
                    if index + 1 < len(timeline.segments)
                    else ""
                )
                diverse = [
                    item
                    for item in filtered
                    if item[1].clip.source_id not in {previous_source, next_source}
                ]
                if diverse:
                    filtered = diverse
            top_window = filtered[: min(8, len(filtered))]
            rank, candidate = rng.choice(top_window)
            used_clip_ids.discard(segment.clip_id)
            change = _replace_segment(segment, candidate, rank)
            changes.append(change)
            used_clip_ids.add(segment.clip_id)
            history.add(segment.clip_id)
            if self.material_store is not None:
                analysis = self.material_store.get(segment.clip_id)
                if analysis and analysis.original_subtitles:
                    plans = plan_subtitle_cleanup(analysis, replacement_text="")
                    if plans:
                        cleanup[segment.segment_id] = [plan.to_dict() for plan in plans]
                        cleanup_plans.extend(plans)
        hypothesis = (
            "固定已验证开头，只测试后续画面"
            if mode == "same_hook_new_body"
            else "固定文案和结构，测试整条视频的画面组合"
        )
        manifest = CreativeVariantManifest(
            creative_family_id=family_id,
            parent_creative_id=self.parent_timeline.project_id,
            variant_id=variant_id,
            mode=mode,
            test_hypothesis=hypothesis,
            locked_hook=mode == "same_hook_new_body",
            locked_cta=preserve_cta,
            hook_seconds=hook_seconds,
            changed_dimensions=["body_visuals"] if mode == "same_hook_new_body" else ["visuals"],
            changes=changes,
            subtitle_cleanup=cleanup,
            subtitle_cleanup_risk=summarize_cleanup_risk(cleanup_plans),
            generated_at=datetime.now(timezone.utc).isoformat(),
            seed=seed,
        )
        timeline.project_id = f"{self.parent_timeline.project_id}_{variant_id}"
        timeline.warnings = [
            *timeline.warnings,
            f"creative_family={family_id}",
            f"variant_mode={mode}",
            f"changed_segments={len(changes)}",
        ]
        return timeline, manifest, skipped
