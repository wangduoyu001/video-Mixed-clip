from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .information_flow_copy import (
    InformationFlowCopyPlanner,
    export_variant_script,
    save_information_flow_plan,
)
from .ollama_adapter import OllamaClient, OllamaError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="information-flow-copy",
        description="把事实输入重写为强钩子、可测试、可审核的信息流口播和字幕方案。",
    )
    parser.add_argument("--config", help="本地JSON配置文件")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="生成稳健、进取和边界合规文案")
    generate.add_argument("--input", required=True, help="UTF-8原始文案文件")
    generate.add_argument("--output", required=True, help="输出方案JSON")
    generate.add_argument("--objective", default="点击或转化")
    generate.add_argument("--platform", default="通用信息流")
    generate.add_argument("--count-per-level", type=int, default=3)
    generate.add_argument("--model", help="本次指定Ollama文本模型")
    generate.add_argument("--export-variant", help="同时导出指定COPY_XXX版本口播文本")
    generate.add_argument("--export-script", help="指定版本口播文本输出路径")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config = load_config(args.config)
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"原始文案不存在：{source}")
    client = OllamaClient(
        base_url=config.local_models.ollama_base_url,
        timeout=config.local_models.ollama_timeout_seconds,
    )
    if not client.is_available():
        raise SystemExit("Ollama不可用，请先启动本地服务")
    try:
        model = client.select_model(
            capability="completion",
            preferred=args.model or config.local_models.text_model,
        )
    except OllamaError as exc:
        raise SystemExit(str(exc)) from exc
    if model is None:
        raise SystemExit("没有可用的Ollama文本模型")
    planner = InformationFlowCopyPlanner(client, model.name)
    plan = planner.generate(
        source_text=source.read_text(encoding="utf-8"),
        objective=args.objective,
        platform=args.platform,
        variants_per_level=args.count_per_level,
    )
    output = save_information_flow_plan(plan, args.output)
    result = {
        "plan": str(output),
        "variants": len(plan.variants),
        "review_required": [
            item.variant_id for item in plan.variants if item.requires_review
        ],
    }
    if args.export_variant:
        if not args.export_script:
            raise SystemExit("使用--export-variant时必须同时提供--export-script")
        script = export_variant_script(plan, args.export_variant, args.export_script)
        result["script"] = str(script)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
