"""Document chunker: paragraph-aware splitting with size bounds."""

from dataclasses import dataclass

MIN_CHUNK_CHARS = 20


@dataclass
class Chunk:
    """A text chunk with its position in the source document."""

    content: str
    chunk_index: int  # 0-based, order within the file
    start: int  # character offset in original text (inclusive)
    end: int  # character offset in original text (exclusive)


class Chunker:
    """Splits text into chunks: greedy paragraph merge + sliding window for oversized paragraphs."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[Chunk]:
        """Split text into Chunks; paragraph-aware, size-bounded."""
        if not text:
            return []

        paragraphs = self._split_paragraphs(text)
        raw_chunks = self._merge_paragraphs(paragraphs)
        return [
            Chunk(content=c, chunk_index=i, start=s, end=e)
            for i, (c, s, e) in enumerate(raw_chunks)
        ]

    def _split_paragraphs(self, text: str) -> list[tuple[str, int, int]]:
        """Split text on double-newlines, returning (content, start, end) triples."""
        paragraphs: list[tuple[str, int, int]] = []
        pos = 0
        for para in text.split("\n\n"):
            start = pos
            end = start + len(para)
            if para.strip():
                paragraphs.append((para, start, end))
            pos = end + 2  # skip the "\n\n" separator
        return paragraphs

    def _merge_paragraphs(
        self, paragraphs: list[tuple[str, int, int]]
    ) -> list[tuple[str, int, int]]:
        """Greedy merge paragraphs up to chunk_size; slide over oversized ones."""
        result: list[tuple[str, int, int]] = []
        buf: list[tuple[str, int, int]] = []
        buf_len = 0

        for para, p_start, p_end in paragraphs:
            para_len = len(para)

            if para_len > self._chunk_size:
                # flush current buffer first
                if buf:
                    result.extend(self._flush_buffer(buf))
                    buf = []
                    buf_len = 0
                # slide over oversized paragraph
                result.extend(self._slide(para, p_start))
                continue

            sep_len = 2 if buf else 0  # "\n\n" between merged paragraphs
            if buf_len + sep_len + para_len > self._chunk_size:
                result.extend(self._flush_buffer(buf))
                buf = []
                buf_len = 0

            buf.append((para, p_start, p_end))
            buf_len = (p_end - buf[0][1]) if buf else 0

        if buf:
            result.extend(self._flush_buffer(buf))

        return [(c, s, e) for c, s, e in result if len(c) >= MIN_CHUNK_CHARS]

    def _flush_buffer(self, buf: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
        """Join buffered paragraphs into a single chunk."""
        content = "\n\n".join(p for p, _, _ in buf)
        start = buf[0][1]
        end = buf[-1][2]
        return [(content, start, end)]

    def _slide(self, para: str, base: int) -> list[tuple[str, int, int]]:
        """Sliding window over a single oversized paragraph."""
        step = max(1, self._chunk_size - self._overlap)
        result: list[tuple[str, int, int]] = []
        pos = 0
        while pos < len(para):
            chunk_text = para[pos : pos + self._chunk_size]
            result.append((chunk_text, base + pos, base + pos + len(chunk_text)))
            pos += step
        return result
