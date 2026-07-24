from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ollama_adapter import OllamaClient


@dataclass(slots=True)
class ComplianceFinding:
    code: str
    level: str
    text: str
    reason: str


@dataclass(slots=True)
class CopyVariant:
    variant_id: str
    risk_level: str
    hook: str
    voiceover: list[str]
    captions: list[str]
    visual_beats: list[str]
    proof_requirements: list[str]
    cta: str
    changed_dimensions: list[str]
    findings: list[ComplianceFinding] = field(default_factory=list)
    requires_review: bool = False


@dataclass(slots=True)
class InformationFlowPlan:
    source_text: str
    objective: str
    platform: str
    audience: list[str]
    immutable_facts: list[str]
    pain_points: list[str]
    benefits: list[str]
    evidence: list[str]
    prohibited_claims: list[str]
    variants: list[CopyVariant]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RISK_RULES: list[tuple[str, str, str, str]] = [
    (r"百分之百|100%|保证|一定能|绝对有效|永久有效", "absolute_guarantee", "high", "绝对化或保证性承诺"),
    (r"稳赚|躺赚|日入|月入|轻松赚|马上赚钱|暴富", "income_claim", "high", "收益承诺需要可靠证据且通常风险较高"),
    (r"最后\d+个|只剩\d+个|马上下架|错过不再有", "scarcity_claim", "medium", "稀缺性必须来自真实库存或活动规则"),
    (r"第一|唯一|全网最好|行业领先|最强", "superiority_claim", "medium", "最高级或比较级主张需要可验证依据"),
    (r"治愈|根治|药到病除|无副作用|减肥\d+斤", "medical_claim", "high", "医疗或身体效果主张需要专门合规审查"),
    (r"官方通知|系统警告|你中奖了|账户异常", "fake_system_message", "high", "不得伪装系统通知或制造虚假状态"),
    (r"不看后悔|必须点开|点击领取|关闭按钮", "forced_click", "medium", "不得使用欺骗性或强迫式点击表达"),
]


def scan_copy_compliance(text: str) -> list[ComplianceFinding]:
    findings: list[ComplianceFinding] = []
    for pattern, code, level, reason in _RISK_RULES:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            findings.append(
                ComplianceFinding(
                    code=code,
                    level=level,
                    text=match.group(0),
                    reason=reason,
                )
            )
    return findings


def _string_list(payload: dict[str, Any], key: str, limit: int = 24) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return list(dict.fromkeys(cleaned))[:limit]


_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "audience": {"type": "array", "items": {"type": "string"}},
        "immutable_facts": {"type": "array", "items": {"type": "string"}},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "benefits": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "prohibited_claims": {"type": "array", "items": {"type": "string"}},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk_level": {
                        "type": "string",
                        "enum": ["stable", "progressive", "boundary_compliant"],
                    },
                    "hook": {"type": "string"},
                    "voiceover": {"type": "array", "items": {"type": "string"}},
                    "captions": {"type": "array", "items": {"type": "string"}},
                    "visual_beats": {"type": "array", "items": {"type": "string"}},
                    "proof_requirements": {"type": "array", "items": {"type": "string"}},
                    "cta": {"type": "string"},
                    "changed_dimensions": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "risk_level",
                    "hook",
                    "voiceover",
                    "captions",
                    "visual_beats",
                    "proof_requirements",
                    "cta",
                    "changed_dimensions",
                ],
            },
        },
    },
    "required": [
        "audience",
        "immutable_facts",
        "pain_points",
        "benefits",
        "evidence",
        "prohibited_claims",
        "variants",
    ],
}


class InformationFlowCopyPlanner:
    def __init__(self, client: OllamaClient, model: str):
        self.client = client
        self.model = model

    def generate(
        self,
        source_text: str,
        objective: str = "点击或转化",
        platform: str = "通用信息流",
        variants_per_level: int = 3,
    ) -> InformationFlowPlan:
        text = source_text.strip()
        if not text:
            raise ValueError("Source copy is empty")
        count = max(1, min(8, int(variants_per_level)))
        prompt = (
            "你是信息流广告素材策划器。用户输入只是事实和方向来源，最终口播与字幕可以重组和改写，"
            "但不可篡改关键事实、虚构证明、伪造稀缺、承诺无法验证的效果或教人绕过平台审核。\n"
            f"平台：{platform}\n目标：{objective}\n每种强度生成数量：{count}\n"
            f"原始输入：\n{text}\n\n"
            "先提取不可改变的事实、受众、痛点、利益点、已有证据和禁止声称内容。"
            "然后分别生成stable、progressive、boundary_compliant三档版本。"
            "boundary_compliant代表在合规范围内提高冲突、悬念和信息缺口，不代表规避审核。"
            "每个版本前三秒必须有明确钩子；口播负责解释，字幕负责压缩重点，画面节拍负责证明。"
            "每个版本只改变少量维度，便于投放测试归因。"
        )
        payload = self.client.generate(
            model=self.model,
            prompt=prompt,
            schema=_PLAN_SCHEMA,
            system="只输出严格结构化的信息流文案方案；所有主张必须可由输入事实或明确列出的证据支持。",
            timeout=max(self.client.timeout, 180.0),
        )
        variants: list[CopyVariant] = []
        raw_variants = payload.get("variants")
        if isinstance(raw_variants, list):
            for index, raw in enumerate(raw_variants, start=1):
                if not isinstance(raw, dict):
                    continue
                risk_level = str(raw.get("risk_level") or "stable")
                if risk_level not in {"stable", "progressive", "boundary_compliant"}:
                    risk_level = "stable"
                hook = str(raw.get("hook") or "").strip()
                voiceover = _string_list(raw, "voiceover", limit=20)
                captions = _string_list(raw, "captions", limit=20)
                cta = str(raw.get("cta") or "").strip()
                combined = "\n".join([hook, *voiceover, *captions, cta])
                findings = scan_copy_compliance(combined)
                variants.append(
                    CopyVariant(
                        variant_id=f"COPY_{index:03d}",
                        risk_level=risk_level,
                        hook=hook,
                        voiceover=voiceover,
                        captions=captions,
                        visual_beats=_string_list(raw, "visual_beats", limit=20),
                        proof_requirements=_string_list(raw, "proof_requirements", limit=20),
                        cta=cta,
                        changed_dimensions=_string_list(raw, "changed_dimensions", limit=4),
                        findings=findings,
                        requires_review=any(item.level in {"medium", "high"} for item in findings),
                    )
                )
        if not variants:
            raise ValueError("The language model returned no usable copy variants")
        return InformationFlowPlan(
            source_text=text,
            objective=objective,
            platform=platform,
            audience=_string_list(payload, "audience"),
            immutable_facts=_string_list(payload, "immutable_facts"),
            pain_points=_string_list(payload, "pain_points"),
            benefits=_string_list(payload, "benefits"),
            evidence=_string_list(payload, "evidence"),
            prohibited_claims=_string_list(payload, "prohibited_claims"),
            variants=variants,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


def save_information_flow_plan(plan: InformationFlowPlan, output_path: str | Path) -> Path:
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def export_variant_script(plan: InformationFlowPlan, variant_id: str, output_path: str | Path) -> Path:
    selected = next((item for item in plan.variants if item.variant_id == variant_id), None)
    if selected is None:
        raise ValueError(f"Copy variant not found: {variant_id}")
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [selected.hook, *selected.voiceover, selected.cta]
    target.write_text("\n".join(item for item in lines if item.strip()) + "\n", encoding="utf-8")
    return target
