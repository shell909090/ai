"""Tests for the Chunker module."""

from elocate.chunker import MIN_CHUNK_CHARS, Chunker


def test_empty_text() -> None:
    c = Chunker()
    assert c.chunk("") == []


def test_short_text_returns_one_chunk() -> None:
    c = Chunker(chunk_size=500)
    text = "Hello world, this is a longer sentence."  # >= 20 chars
    chunks = c.chunk(text)
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert chunks[0].chunk_index == 0
    assert chunks[0].start == 0
    assert chunks[0].end == len(text)


def test_offsets_span_original_text() -> None:
    """start/end offsets must be valid positions within the original text."""
    c = Chunker(chunk_size=500)
    text = (
        "First paragraph with some content.\n\n"
        "Second paragraph with more content.\n\n"
        "Third paragraph here."
    )
    chunks = c.chunk(text)
    for chunk in chunks:
        assert 0 <= chunk.start <= chunk.end <= len(text)
        # content must contain the stripped lines (LF-only source: direct match holds)
        assert text[chunk.start : chunk.end] == chunk.content


def test_chunk_index_consecutive() -> None:
    c = Chunker(chunk_size=50, overlap=10)
    text = "A" * 200
    chunks = c.chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_greedy_merge_short_paragraphs() -> None:
    c = Chunker(chunk_size=200)
    text = "Short paragraph with content.\n\nAnother paragraph here.\n\nThird paragraph again."
    chunks = c.chunk(text)
    # all three are short enough to merge into one
    assert len(chunks) == 1
    assert "Short paragraph" in chunks[0].content
    assert "Third paragraph" in chunks[0].content


def test_paragraphs_split_when_over_limit() -> None:
    c = Chunker(chunk_size=40)
    # each paragraph ~30 chars, two won't fit in 40 (30+2+30=62 > 40)
    p = "1234567890 abcdefghij 1234567890"  # 31 chars
    text = f"{p}\n\n{p}\n\n{p}"
    chunks = c.chunk(text)
    assert len(chunks) >= 2


def test_oversized_paragraph_sliding_window() -> None:
    c = Chunker(chunk_size=30, overlap=5)
    long_para = "X" * 100
    chunks = c.chunk(long_para)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= 30


def test_discard_small_chunks() -> None:
    c = Chunker(chunk_size=500)
    # tiny paragraph under MIN_CHUNK_CHARS
    text = "Hi\n\nThis is a longer paragraph that will be kept and has enough content."
    chunks = c.chunk(text)
    for chunk in chunks:
        assert len(chunk.content) >= MIN_CHUNK_CHARS


def test_single_newline_lines_merge_into_one_chunk() -> None:
    """Lines separated by single newlines are treated as separate units but merged if they fit."""
    c = Chunker(chunk_size=500)
    text = "Line one is here\nLine two is here\nLine three is here"
    chunks = c.chunk(text)
    assert len(chunks) == 1
    assert "Line one is here" in chunks[0].content
    assert "Line three is here" in chunks[0].content


def test_crlf_paragraphs_split_correctly() -> None:
    """CRLF line endings must not prevent paragraph detection."""
    c = Chunker(chunk_size=500)
    text = "First paragraph here.\r\n\r\nSecond paragraph here."
    chunks = c.chunk(text)
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0].content
    assert "Second paragraph" in chunks[0].content


def test_multiple_blank_lines_filtered() -> None:
    """Multiple consecutive blank lines between paragraphs are handled correctly."""
    c = Chunker(chunk_size=500)
    text = "Para one with enough content.\n\n\n\nPara two with enough content."
    chunks = c.chunk(text)
    assert len(chunks) == 1
    assert "Para one" in chunks[0].content
    assert "Para two" in chunks[0].content


def test_overlap_in_sliding_window() -> None:
    c = Chunker(chunk_size=30, overlap=10)
    text = "A" * 100  # oversized: will be slid
    chunks = c.chunk(text)
    # step = 30-10 = 20; positions: 0, 20, 40, 60, 80
    assert chunks[0].start == 0
    assert chunks[1].start == 20
