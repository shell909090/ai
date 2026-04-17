"""Document chunker: paragraph-aware splitting with size bounds."""

from dataclasses import dataclass


MIN_CHUNK_CHARS = 20


@dataclass
class Chunk:
    """A text chunk with its position in the source document."""

    content: str
    chunk_index: int  # 0-based, order within the file
    start: int        # character offset in original text (inclusive)
    end: int          # character offset in original text (exclusive)


class Chunker:
    """Splits text into chunks: greedy paragraph merge + sliding window for oversized paragraphs."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[Chunk]:
        """Split text into Chunks; paragraph-aware, size-bounded."""
        raise NotImplementedError
