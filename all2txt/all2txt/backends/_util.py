from pathlib import Path


def extract_audio(path: Path) -> Path:
    """Extract audio track from a video file to a temporary WAV file.

    Returns the path to the temp file; caller must delete it after use.
    Only call for video MIME types; pass audio files directly to ASR.
    """
    raise NotImplementedError
