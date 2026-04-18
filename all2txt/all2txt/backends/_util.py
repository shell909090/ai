import os
import subprocess
import tempfile
from pathlib import Path

_VIDEO_MIMES = frozenset(
    {
        "video/mp4",
        "video/x-matroska",
        "video/quicktime",
        "video/x-msvideo",
        "video/webm",
    }
)


def extract_audio(path: Path) -> Path:
    """Extract audio track from a video file to a temporary WAV file.

    Returns the path to the temp file; caller must delete it after use.
    Only call for video MIME types; pass audio files directly to ASR.
    """
    fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                tmp_wav,
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        os.unlink(tmp_wav)
        raise
    return Path(tmp_wav)
