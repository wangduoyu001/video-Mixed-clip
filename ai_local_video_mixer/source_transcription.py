from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .catalog import MediaCatalog
from .config import TranscriptionConfig
from .models import MediaClip, MediaSource, ModelLocation
from .transcription import (
    TranscriptionError,
    TranscriptionResult,
    resolve_whisper_model,
    run_whisper_cli,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_transcripts (
    source_id TEXT NOT NULL,
    model TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    transcript_json TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT NOT NULL,
    duration REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, model)
);
CREATE INDEX IF NOT EXISTS idx_source_transcripts_source
ON source_transcripts(source_id);
"""


@dataclass(slots=True)
class SourceTranscriptionSummary:
    model: str
    requested: int = 0
    transcribed: int = 0
    unchanged: int = 0
    skipped_no_audio: int = 0
    clips_updated: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SourceTranscriptStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(_SCHEMA)

    def metadata(self, source_id: str, model: str) -> tuple[str, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT fingerprint, text
                FROM source_transcripts
                WHERE source_id = ? AND model = ?
                """,
                (source_id, model),
            ).fetchone()
        if not row:
            return None
        return str(row["fingerprint"]), str(row["text"])

    def upsert(
        self,
        source: MediaSource,
        model: str,
        result: TranscriptionResult,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_transcripts(
                    source_id, model, fingerprint, transcript_json,
                    text, language, duration
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, model) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    transcript_json=excluded.transcript_json,
                    text=excluded.text,
                    language=excluded.language,
                    duration=excluded.duration,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    source.source_id,
                    model,
                    source.fingerprint,
                    json.dumps(result.to_dict(), ensure_ascii=False),
                    result.text,
                    result.language,
                    result.duration,
                ),
            )

    def load(self, source_id: str, model: str) -> TranscriptionResult | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT transcript_json
                FROM source_transcripts
                WHERE source_id = ? AND model = ?
                """,
                (source_id, model),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(str(row["transcript_json"]))
        from .transcription import parse_whisper_payload

        return parse_whisper_payload(
            payload,
            audio_path=payload.get("audio_path") or source_id,
            model=model,
            duration_override=float(payload.get("duration") or 0.0),
        )


def transcript_text_for_clip(result: TranscriptionResult, clip: MediaClip) -> str:
    parts: list[str] = []
    for segment in result.segments:
        overlap_start = max(segment.start, clip.source_start)
        overlap_end = min(segment.end, clip.source_end)
        if overlap_end - overlap_start <= 0.05:
            continue
        text = segment.text.strip()
        if text:
            parts.append(text)
    return " ".join(dict.fromkeys(parts)).strip()


def _base_visual_description(description: str) -> str:
    lines = [
        line.strip()
        for line in description.splitlines()
        if line.strip() and not line.strip().startswith("原素材对白：")
    ]
    return "\n".join(lines).strip()


class SourceTranscriptIndexer:
    def __init__(
        self,
        catalog: MediaCatalog,
        store: SourceTranscriptStore,
        whisper_path: str | None,
        model: str | None,
        config: TranscriptionConfig,
        output_root: str | Path,
    ):
        self.catalog = catalog
        self.store = store
        self.whisper_path = whisper_path
        self.model = model
        self.config = config
        self.output_root = Path(output_root)

    @classmethod
    def resolve_model(
        cls,
        configured: str,
        locations: list[ModelLocation],
        config: TranscriptionConfig,
    ) -> str | None:
        return resolve_whisper_model(
            configured,
            locations,
            allow_download=config.allow_model_download,
        )

    def build(
        self,
        limit: int | None = None,
        force: bool = False,
    ) -> SourceTranscriptionSummary:
        sources = self.catalog.list_sources()
        if limit is not None:
            sources = sources[: max(0, limit)]
        summary = SourceTranscriptionSummary(
            model=self.model or "",
            requested=len(sources),
        )
        audio_sources = [source for source in sources if source.has_audio]
        summary.skipped_no_audio = len(sources) - len(audio_sources)
        if not audio_sources:
            return summary
        if not self.whisper_path:
            raise TranscriptionError("Whisper CLI was not discovered")
        if not self.model:
            raise TranscriptionError("No Whisper model is available for source transcription")

        clips_by_source: dict[str, list[MediaClip]] = {}
        for clip in self.catalog.list_clips(usable_only=False):
            clips_by_source.setdefault(clip.source_id, []).append(clip)

        for source in audio_sources:
            metadata = self.store.metadata(source.source_id, self.model)
            if metadata and metadata[0] == source.fingerprint and not force:
                summary.unchanged += 1
                cached = self.store.load(source.source_id, self.model)
                if cached is not None:
                    summary.clips_updated += self._apply_to_clips(
                        clips_by_source.get(source.source_id, []), cached
                    )
                continue
            try:
                result = run_whisper_cli(
                    whisper_path=self.whisper_path,
                    audio_path=source.source_path,
                    model=self.model,
                    output_dir=self.output_root / source.source_id,
                    config=self.config,
                    duration_override=source.duration,
                )
            except (TranscriptionError, FileNotFoundError, OSError, ValueError) as exc:
                summary.failed += 1
                summary.errors.append(f"{source.source_id}: {exc}")
                continue
            self.store.upsert(source, self.model, result)
            summary.transcribed += 1
            summary.clips_updated += self._apply_to_clips(
                clips_by_source.get(source.source_id, []), result
            )
        return summary

    def _apply_to_clips(
        self,
        clips: list[MediaClip],
        result: TranscriptionResult,
    ) -> int:
        updated = 0
        for clip in clips:
            dialogue = transcript_text_for_clip(result, clip)
            old_tags = [
                item
                for item in clip.tags
                if not item.startswith("dialogue:") and item != "no_dialogue_in_clip"
            ]
            visual = _base_visual_description(clip.description)
            if dialogue:
                clip.tags = list(
                    dict.fromkeys([*old_tags, f"dialogue:{dialogue[:160]}"])
                )[:64]
                clip.description = (
                    f"{visual}\n原素材对白：{dialogue}"
                    if visual
                    else f"原素材对白：{dialogue}"
                )
            else:
                clip.tags = list(
                    dict.fromkeys([*old_tags, "no_dialogue_in_clip"])
                )[:64]
                clip.description = visual
            self.catalog.upsert_clip(clip)
            updated += 1
        return updated
