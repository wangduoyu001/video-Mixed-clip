from ai_local_video_mixer.config import RuntimeConfig
from ai_local_video_mixer.pipeline import ScriptMixerPipeline


def test_package_is_standalone() -> None:
    assert ScriptMixerPipeline.__module__.startswith("ai_local_video_mixer")


def test_source_processing_limit_is_40_seconds() -> None:
    assert RuntimeConfig().media_scan.maximum_source_process_seconds == 40.0
