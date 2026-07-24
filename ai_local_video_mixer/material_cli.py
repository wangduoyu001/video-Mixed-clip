from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .catalog import MediaCatalog
from .config import load_config
from .environment import discover_environment
from .material_intelligence import (
    MaterialIntelligenceEngine,
    MaterialIntelligenceStore,
    MaterialVisionAnalyzer,
)
from .ollama_adapter import OllamaClient, OllamaError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="material-intelligence",
        description="多帧识别素材画面、道具、产品包装、原字幕、暗示和表现手法。",
    )
    parser.add_argument("--config", help="本地JSON配置文件")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="分析素材库并将不安全镜头硬过滤")
    analyze.add_argument("--limit", type=int)
    analyze.add_argument("--force", action="store_true")
    analyze.add_argument("--model", help="本次指定Ollama视觉模型")

    subparsers.add_parser("status", help="显示包装、字幕和可用镜头统计")
    inspect = subparsers.add_parser("inspect", help="查看一个镜头的完整分析")
    inspect.add_argument("clip_id")
    return parser


def _status(database_path: str | Path) -> dict:
    path = Path(database_path)
    if not path.exists():
        return {"database": str(path), "available": False}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shot_intelligence'"
        ).fetchone()
        if not table:
            return {
                "database": str(path),
                "available": True,
                "analyzed": 0,
                "accepted": 0,
                "rejected": 0,
                "packaging_rejected": 0,
                "contains_original_subtitles": 0,
            }
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS analyzed,
                SUM(CASE WHEN usable = 1 THEN 1 ELSE 0 END) AS accepted,
                SUM(CASE WHEN usable = 0 THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN contains_product_packaging = 1 THEN 1 ELSE 0 END)
                    AS packaging_rejected,
                SUM(CASE WHEN contains_original_subtitles = 1 THEN 1 ELSE 0 END)
                    AS contains_original_subtitles
            FROM shot_intelligence
            """
        ).fetchone()
    return {
        "database": str(path),
        "available": True,
        "analyzed": int(row["analyzed"] or 0),
        "accepted": int(row["accepted"] or 0),
        "rejected": int(row["rejected"] or 0),
        "packaging_rejected": int(row["packaging_rejected"] or 0),
        "contains_original_subtitles": int(row["contains_original_subtitles"] or 0),
    }


def main() -> int:
    args = _build_parser().parse_args()
    config = load_config(args.config)
    store = MaterialIntelligenceStore(config.database_path)

    if args.command == "status":
        print(json.dumps(_status(config.database_path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect":
        analysis = store.get(args.clip_id)
        if analysis is None:
            raise SystemExit(f"No material analysis found for clip: {args.clip_id}")
        print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))
        return 0

    discovery = discover_environment(config.discovery)
    ffmpeg = discovery.tools.get("ffmpeg")
    if not ffmpeg or not ffmpeg.executable:
        raise SystemExit("ffmpeg不可用，无法进行逐帧素材识别")

    client = OllamaClient(
        base_url=config.local_models.ollama_base_url,
        timeout=config.local_models.ollama_timeout_seconds,
    )
    if not client.is_available():
        raise SystemExit("Ollama不可用，请先启动本地服务")
    try:
        model = client.select_model(
            capability="vision",
            preferred=args.model or config.local_models.vision_model,
        )
    except OllamaError as exc:
        raise SystemExit(str(exc)) from exc
    if model is None:
        raise SystemExit("没有可用的Ollama视觉模型")

    catalog = MediaCatalog(config.database_path)
    catalog.initialize()
    engine = MaterialIntelligenceEngine(
        catalog=catalog,
        store=store,
        analyzer=MaterialVisionAnalyzer(client, model.name),
        ffmpeg_path=ffmpeg.executable,
        config=config.material_intelligence,
    )
    summary = engine.analyze_catalog(limit=args.limit, force=args.force)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.failed and config.material_intelligence.fail_closed_on_analysis_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
