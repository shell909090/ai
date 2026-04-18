"""Tests for ASR (automatic speech recognition) backends and audio utilities."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_backends._helpers import _make_module

# ===========================================================================
# OpenAIWhisperExtractor
# ===========================================================================


class TestOpenAIWhisperExtractor:
    def test_available_returns_false_when_openai_missing(self) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        with patch.dict(sys.modules, {"openai": None}):
            assert OpenAIWhisperExtractor().available() is False

    def test_available_returns_true_when_openai_present(self) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock()
        with patch.dict(sys.modules, {"openai": fake_openai}):
            assert OpenAIWhisperExtractor().available() is True

    def test_extract_audio_file_calls_api(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "audio.mp3"
        fake_path.write_bytes(b"audio data")

        mock_result = MagicMock()
        mock_result.text = "transcribed text"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIWhisperExtractor(config={"_mime": "audio/mpeg"})
            result = extractor.extract(fake_path)

        assert result == "transcribed text"
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["response_format"] == "text"

    def test_extract_video_file_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "video.mp4"
        fake_path.write_bytes(b"video data")
        fake_audio_path = tmp_path / "audio.wav"
        fake_audio_path.write_bytes(b"audio data")

        mock_result = "transcribed"  # str response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = OpenAIWhisperExtractor(config={"_mime": "video/mp4"})
            result = extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_unlink.assert_called_once_with(fake_audio_path)
        assert result == "transcribed"

    def test_extract_passes_language_when_configured(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import OpenAIWhisperExtractor

        fake_path = tmp_path / "audio.mp3"
        fake_path.write_bytes(b"data")

        mock_result = MagicMock()
        mock_result.text = "text"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIWhisperExtractor(config={"_mime": "audio/mpeg", "language": "zh"})
            extractor.extract(fake_path)

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "zh"


# ===========================================================================
# FasterWhisperExtractor
# ===========================================================================


class TestFasterWhisperExtractor:
    def test_available_returns_false_when_faster_whisper_missing(self) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        with patch.dict(sys.modules, {"faster_whisper": None}):
            assert FasterWhisperExtractor().available() is False

    def test_available_returns_true_when_faster_whisper_present(self) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock()
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            assert FasterWhisperExtractor().available() is True

    def test_extract_audio_joins_segments(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_path = tmp_path / "audio.wav"
        fake_path.write_bytes(b"data")

        seg1 = MagicMock()
        seg1.text = "  Hello  "
        seg2 = MagicMock()
        seg2.text = " world  "

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            extractor = FasterWhisperExtractor(
                config={"_mime": "audio/x-wav", "model": "small", "device": "cuda"}
            )
            result = extractor.extract(fake_path)

        fake_fw.WhisperModel.assert_called_once_with("small", device="cuda")
        assert result == "Hello world"

    def test_extract_video_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import FasterWhisperExtractor

        fake_path = tmp_path / "video.mkv"
        fake_path.write_bytes(b"data")
        fake_audio_path = tmp_path / "tmp.wav"
        fake_audio_path.write_bytes(b"audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())

        fake_fw = _make_module("faster_whisper")
        fake_fw.WhisperModel = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"faster_whisper": fake_fw}),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = FasterWhisperExtractor(config={"_mime": "video/x-matroska"})
            extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_unlink.assert_called_once_with(fake_audio_path)


# ===========================================================================
# WhisperLocalExtractor
# ===========================================================================


class TestWhisperLocalExtractor:
    def test_available_returns_false_when_whisper_missing(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        with patch.dict(sys.modules, {"whisper": None}):
            assert WhisperLocalExtractor().available() is False

    def test_available_returns_false_when_ffmpeg_missing(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_whisper = _make_module("whisper")
        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("shutil.which", return_value=None),
        ):
            assert WhisperLocalExtractor().available() is False

    def test_available_returns_true_when_both_present(self) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_whisper = _make_module("whisper")
        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            assert WhisperLocalExtractor().available() is True

    def test_extract_audio_transcribes_and_returns_text(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "audio.flac"
        fake_path.write_bytes(b"data")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "transcription result"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"whisper": fake_whisper}):
            extractor = WhisperLocalExtractor(config={"_mime": "audio/flac", "model": "small"})
            result = extractor.extract(fake_path)

        fake_whisper.load_model.assert_called_once_with("small")
        mock_model.transcribe.assert_called_once_with(str(fake_path))
        assert result == "transcription result"

    def test_extract_video_extracts_audio_first(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "video.mp4"
        fake_path.write_bytes(b"data")
        fake_audio_path = tmp_path / "tmp.wav"
        fake_audio_path.write_bytes(b"audio")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "video transcription"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"whisper": fake_whisper}),
            patch(
                "all2txt.backends.asr.extract_audio", return_value=fake_audio_path
            ) as mock_extract,
            patch("os.unlink") as mock_unlink,
        ):
            extractor = WhisperLocalExtractor(config={"_mime": "video/mp4"})
            result = extractor.extract(fake_path)

        mock_extract.assert_called_once_with(fake_path)
        mock_model.transcribe.assert_called_once_with(str(fake_audio_path))
        mock_unlink.assert_called_once_with(fake_audio_path)
        assert result == "video transcription"

    def test_extract_passes_language_kwarg(self, tmp_path: Path) -> None:
        from all2txt.backends.asr import WhisperLocalExtractor

        fake_path = tmp_path / "audio.wav"
        fake_path.write_bytes(b"data")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "text"}

        fake_whisper = _make_module("whisper")
        fake_whisper.load_model = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"whisper": fake_whisper}):
            extractor = WhisperLocalExtractor(config={"_mime": "audio/x-wav", "language": "fr"})
            extractor.extract(fake_path)

        mock_model.transcribe.assert_called_once_with(str(fake_path), language="fr")


# ===========================================================================
# _util.extract_audio
# ===========================================================================


class TestExtractAudio:
    def test_extract_audio_calls_ffmpeg_with_correct_args(self, tmp_path: Path) -> None:
        from all2txt.backends._util import extract_audio

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"data")

        fake_fd = 5
        fake_tmp_wav = str(tmp_path / "tmp_audio.wav")

        with (
            patch("tempfile.mkstemp", return_value=(fake_fd, fake_tmp_wav)),
            patch("os.close") as mock_close,
            patch("subprocess.run") as mock_run,
        ):
            result = extract_audio(fake_video)

        mock_close.assert_called_once_with(fake_fd)
        mock_run.assert_called_once_with(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(fake_video),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                fake_tmp_wav,
            ],
            capture_output=True,
            check=True,
        )
        assert result == Path(fake_tmp_wav)

    def test_extract_audio_cleans_up_temp_file_on_failure(self, tmp_path: Path) -> None:
        from all2txt.backends._util import extract_audio

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"data")

        fake_fd = 5
        fake_tmp_wav = str(tmp_path / "tmp_audio.wav")

        with (
            patch("tempfile.mkstemp", return_value=(fake_fd, fake_tmp_wav)),
            patch("os.close"),
            patch("subprocess.run", side_effect=RuntimeError("ffmpeg failed")),
            patch("os.unlink") as mock_unlink,
        ):
            with pytest.raises(RuntimeError, match="ffmpeg failed"):
                extract_audio(fake_video)

        mock_unlink.assert_called_once_with(fake_tmp_wav)


# ===========================================================================
# _util._VIDEO_MIMES completeness (R010)
# ===========================================================================


class TestVideoMimesCompleteness:
    def test_video_mimes_includes_mpeg_and_ogg(self) -> None:
        from all2txt.backends._util import _VIDEO_MIMES

        assert "video/mpeg" in _VIDEO_MIMES
        assert "video/ogg" in _VIDEO_MIMES

    def test_asr_uses_util_video_mimes_not_own_tuple(self) -> None:
        from all2txt.backends import asr
        from all2txt.backends._util import _VIDEO_MIMES

        # _VIDEO_MIME_TUPLE in asr.py must be derived from _VIDEO_MIMES
        assert set(asr._VIDEO_MIME_TUPLE) == _VIDEO_MIMES
