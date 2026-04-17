import shutil
from pathlib import Path
from typing import Any

from ..core.base import Extractor
from ..core.registry import registry

_AUDIO_MIMES = (
    "audio/mpeg",       # .mp3
    "audio/x-wav",      # .wav
    "audio/wav",
    "audio/ogg",        # .ogg / .opus
    "audio/flac",       # .flac
    "audio/x-flac",
    "audio/mp4",        # .m4a
    "audio/aac",        # .aac
    "audio/webm",
)

_VIDEO_MIMES = (
    "video/mp4",            # .mp4
    "video/x-matroska",     # .mkv
    "video/quicktime",      # .mov
    "video/x-msvideo",      # .avi
    "video/webm",
)


@registry.register(*_AUDIO_MIMES, *_VIDEO_MIMES)
class OpenAIWhisperExtractor(Extractor):
    """Transcribe audio/video via OpenAI Transcription API (whisper-1).

    Video files require ffmpeg to extract the audio track before upload.

    Config keys:
      model           (str): Model ID. Default: "whisper-1".
      language        (str): BCP-47 language code hint, e.g. "zh". Optional.
      response_format (str): "text" (default) | "srt" | "vtt" | "verbose_json".
    """

    name = "openai_whisper"
    priority = 30

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._model: str = self._cfg.get("model", "whisper-1")
        self._language: str | None = self._cfg.get("language")
        self._response_format: str = self._cfg.get("response_format", "text")

    def available(self) -> bool:
        """Check that openai package and ffmpeg (for video) are installed."""
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Extract audio if video, then call openai.audio.transcriptions.create."""
        raise NotImplementedError


@registry.register(*_AUDIO_MIMES, *_VIDEO_MIMES)
class FasterWhisperExtractor(Extractor):
    """Transcribe via faster-whisper (local CTranslate2-based Whisper).

    Video files require ffmpeg to extract the audio track first.

    Config keys:
      model    (str): Model size or path. Default: "base".
      language (str): Language code hint. Optional.
      device   (str): "cpu" (default) | "cuda".
    """

    name = "faster_whisper"
    priority = 33

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._model: str = self._cfg.get("model", "base")
        self._language: str | None = self._cfg.get("language")
        self._device: str = self._cfg.get("device", "cpu")

    def available(self) -> bool:
        """Check that faster-whisper is installed."""
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Load model, transcribe segments, join into plain text."""
        raise NotImplementedError


@registry.register(*_AUDIO_MIMES, *_VIDEO_MIMES)
class WhisperLocalExtractor(Extractor):
    """Transcribe via openai-whisper (original local implementation).

    Video files require ffmpeg to extract the audio track first.

    Config keys:
      model    (str): Model name: tiny/base/small/medium/large. Default: "base".
      language (str): Language code hint. Optional.
    """

    name = "whisper_local"
    priority = 35

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._model: str = self._cfg.get("model", "base")
        self._language: str | None = self._cfg.get("language")

    def available(self) -> bool:
        """Check that openai-whisper and ffmpeg are installed."""
        try:
            import whisper  # noqa: F401
        except ImportError:
            return False
        return shutil.which("ffmpeg") is not None

    def extract(self, path: Path) -> str:
        """Load whisper model, transcribe file, return text field."""
        raise NotImplementedError
