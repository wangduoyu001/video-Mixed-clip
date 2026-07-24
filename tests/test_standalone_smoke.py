from ai_local_video_mixer.config import RuntimeConfig
from ai_local_video_mixer.pipeline import ScriptMixerPipeline


def test_package_is_standalone() -> None:
    assert ScriptMixerPipeline.__module__.startswith("ai_local_video_mixer")


def test_full_source_is_indexed_by_default() -> None:
    assert RuntimeConfig().media_scan.maximum_source_process_seconds == 0.0


def test_source_usage_is_limited_during_editing_not_scanning() -> None:
    assert RuntimeConfig().mixing.max_single_source_seconds == 4.0
