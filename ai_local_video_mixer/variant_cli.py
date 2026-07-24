from __future__ import annotations

import argparse
import json

from .config import load_config
from .creative_variants import CreativeVariantGenerator
from .material_intelligence import MaterialIntelligenceStore
from .review import resolve_project_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creative-variants",
        description="围绕跑量母素材生成可追踪、单变量的批量裂变版本。",
    )
    parser.add_argument("--config", help="本地JSON配置文件")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="生成同钩子换后续或同文案换画面的变体")
    generate.add_argument("project", help="项目ID或项目目录")
    generate.add_argument(
        "--mode",
        choices=["same_hook_new_body", "same_script_new_visuals"],
        default="same_hook_new_body",
    )
    generate.add_argument("--count", type=int)
    generate.add_argument("--hook-seconds", type=float)
    generate.add_argument("--preserve-cta", action="store_true")
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--family-id")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config = load_config(args.config)
    project_dir = resolve_project_dir(args.project, config.output_root)
    store = MaterialIntelligenceStore(config.database_path)
    generator = CreativeVariantGenerator(
        project_dir=project_dir,
        config=config.creative_variants,
        material_store=store,
    )
    summary = generator.generate(
        count=args.count,
        mode=args.mode,
        hook_seconds=args.hook_seconds,
        preserve_cta=args.preserve_cta,
        seed=args.seed,
        creative_family_id=args.family_id,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
