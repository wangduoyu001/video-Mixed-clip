from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import MediaCatalog
from .config import load_config
from .environment import discover_environment
from .source_transcription import SourceTranscriptIndexer, SourceTranscriptStore
from .transcription import TranscriptionError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="source-transcripts",
        description="识别原视频对白并把时间对齐文本写回镜头素材库。",
    )
    parser.add_argument("--config", help="本地JSON配置文件")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="批量转写带音轨的原素材")
    build.add_argument("--limit", type=int)
    build.add_argument("--force", action="store_true")
    build.add_argument("--model", help="本次指定Whisper模型或本地.pt路径")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config = load_config(args.config)
    discovery = discover_environment(config.discovery)
    whisper = discovery.tools.get("whisper")
    model = SourceTranscriptIndexer.resolve_model(
        args.model or config.local_models.speech_model,
        discovery.models.get("whisper", []),
        config.transcription,
    )
    catalog = MediaCatalog(config.database_path)
    catalog.initialize()
    store = SourceTranscriptStore(config.database_path)
    indexer = SourceTranscriptIndexer(
        catalog=catalog,
        store=store,
        whisper_path=whisper.executable if whisper else None,
        model=model,
        config=config.transcription,
        output_root=Path(config.transcription.output_root) / "source_material",
    )
    try:
        summary = indexer.build(limit=args.limit, force=args.force)
    except TranscriptionError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
