"""Tests for ThinkTagParser streaming parser."""

from little_agent.agent.protocol import SessionUpdate
from little_agent.backends.openai import ThinkTagParser


def collect_updates(parser: ThinkTagParser, chunks: list[str]) -> list[SessionUpdate]:
    """Feed chunks and flush, return all updates."""
    updates: list[SessionUpdate] = []
    for chunk in chunks:
        updates.extend(parser.feed(chunk))
    updates.extend(parser.flush())
    return updates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_texts(updates: list[SessionUpdate]) -> list[str]:
    return [u.data["text"] for u in updates if u.type == "agent_message_chunk"]


def _thinking_texts(updates: list[SessionUpdate]) -> list[str]:
    return [u.data["text"] for u in updates if u.type == "thinking_chunk"]


def _all_texts_joined(updates: list[SessionUpdate]) -> str:
    return "".join(str(u.data["text"]) for u in updates)


# ---------------------------------------------------------------------------
# Scenario 1: no tags, single chunk
# ---------------------------------------------------------------------------


def test_no_tags_single_chunk_produces_agent_message_chunk() -> None:
    """All content without tags is emitted as agent_message_chunk."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["hello world"])
    assert all(u.type == "agent_message_chunk" for u in updates)
    assert "".join(_agent_texts(updates)) == "hello world"


# ---------------------------------------------------------------------------
# Scenario 2: no tags, multiple chunks
# ---------------------------------------------------------------------------


def test_no_tags_multiple_chunks_all_agent_message_chunks() -> None:
    """Multiple chunks without tags all produce agent_message_chunk updates."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["foo", " bar", " baz"])
    assert all(u.type == "agent_message_chunk" for u in updates)
    assert "".join(_agent_texts(updates)) == "foo bar baz"


# ---------------------------------------------------------------------------
# Scenario 3: complete tag in a single chunk
# ---------------------------------------------------------------------------


def test_complete_tag_in_single_chunk() -> None:
    """<think>...</think> in one chunk splits into correct update types."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["hello<think>thinking</think>world"])

    assert _agent_texts(updates) == ["hello", "world"] or (
        "".join(_agent_texts(updates)) == "helloworld"
    )
    assert "".join(_thinking_texts(updates)) == "thinking"

    # Tags must not appear anywhere in emitted text.
    for u in updates:
        assert "<think>" not in str(u.data["text"])
        assert "</think>" not in str(u.data["text"])


def test_complete_tag_order_of_updates() -> None:
    """Updates from 'hello<think>thinking</think>world' arrive in correct order."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["hello<think>thinking</think>world"])

    types = [u.type for u in updates]
    # agent_message_chunk for "hello", thinking_chunk for inner content,
    # agent_message_chunk for "world" — in that order.
    assert types.index("agent_message_chunk") < types.index("thinking_chunk")
    last_agent = max(i for i, u in enumerate(updates) if u.type == "agent_message_chunk")
    last_thinking = max(i for i, u in enumerate(updates) if u.type == "thinking_chunk")
    assert last_thinking < last_agent


# ---------------------------------------------------------------------------
# Scenario 4: <think> tag split across chunk boundary
# ---------------------------------------------------------------------------


def test_open_tag_split_across_chunks() -> None:
    """<think> split across two chunks is correctly recognised."""
    parser = ThinkTagParser()

    # First chunk ends mid-tag; no thinking update should arrive yet.
    updates_first = parser.feed("hel<thi")
    assert all(u.type == "agent_message_chunk" for u in updates_first)
    # "hel" is safe to emit, but nothing inside the potential tag.
    assert all("<thi" not in str(u.data["text"]) for u in updates_first)

    # Second chunk completes the tag and adds thinking content.
    updates_second = parser.feed("nk>thinking content")
    updates_flush = parser.flush()

    all_updates = updates_first + updates_second + updates_flush
    assert "".join(_thinking_texts(all_updates)) == "thinking content"
    # "hel" should have been emitted as agent_message_chunk.
    assert "hel" in "".join(_agent_texts(all_updates))
    # The reconstructed tag must not appear in any text.
    for u in all_updates:
        assert "<think>" not in str(u.data["text"])


# ---------------------------------------------------------------------------
# Scenario 5: </think> tag split across chunk boundary
# ---------------------------------------------------------------------------


def test_close_tag_split_across_chunks() -> None:
    """</think> split across two chunks is correctly recognised."""
    parser = ThinkTagParser()

    updates: list[SessionUpdate] = []
    updates.extend(parser.feed("<think>inner content</thi"))
    updates.extend(parser.feed("nk>after"))
    updates.extend(parser.flush())

    assert "".join(_thinking_texts(updates)) == "inner content"
    assert "after" in "".join(_agent_texts(updates))

    for u in updates:
        assert "</think>" not in str(u.data["text"])
        assert "<think>" not in str(u.data["text"])


# ---------------------------------------------------------------------------
# Scenario 6: unclosed <think> — flush emits remaining buffer as thinking_chunk
# ---------------------------------------------------------------------------


def test_unclosed_think_tag_flushed_as_thinking_chunk() -> None:
    """Content inside an unclosed <think> is flushed as thinking_chunk."""
    parser = ThinkTagParser()
    updates: list[SessionUpdate] = []
    updates.extend(parser.feed("<think>some"))
    updates.extend(parser.flush())

    thinking = _thinking_texts(updates)
    assert "some" in "".join(thinking)
    # All content after <think> must be thinking_chunk.
    for u in updates:
        if u.type != "agent_message_chunk":
            assert u.type == "thinking_chunk"


# ---------------------------------------------------------------------------
# Scenario 7: content after </think> becomes agent_message_chunk
# ---------------------------------------------------------------------------


def test_content_after_close_tag_is_agent_message_chunk() -> None:
    """Text that follows </think> is emitted as agent_message_chunk."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["<think>thinking</think>after"])

    assert "after" in "".join(_agent_texts(updates))
    assert "thinking" in "".join(_thinking_texts(updates))


# ---------------------------------------------------------------------------
# Scenario 8: multiple <think> blocks
# ---------------------------------------------------------------------------


def test_multiple_think_blocks_both_parsed() -> None:
    """Two separate <think>...</think> blocks are both routed as thinking_chunk."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["before<think>first</think>middle<think>second</think>end"])

    thinking = "".join(_thinking_texts(updates))
    agent = "".join(_agent_texts(updates))

    assert "first" in thinking
    assert "second" in thinking
    assert "before" in agent
    assert "middle" in agent
    assert "end" in agent

    for u in updates:
        assert "<think>" not in str(u.data["text"])
        assert "</think>" not in str(u.data["text"])


# ---------------------------------------------------------------------------
# Scenario 9: <think></think> with no content — no non-empty updates emitted
# ---------------------------------------------------------------------------


def test_empty_think_block_produces_no_nonempty_updates() -> None:
    """<think></think> should not emit SessionUpdates with empty text."""
    parser = ThinkTagParser()
    updates = collect_updates(parser, ["<think></think>"])

    for u in updates:
        assert str(u.data["text"]) != "", f"Empty text emitted in update of type {u.type}"


# ---------------------------------------------------------------------------
# Additional edge-case: empty string feed produces no updates
# ---------------------------------------------------------------------------


def test_empty_feed_produces_no_updates() -> None:
    """Feeding an empty string must not emit any SessionUpdate."""
    parser = ThinkTagParser()
    updates = parser.feed("")
    assert updates == []


def test_flush_on_empty_parser_produces_no_updates() -> None:
    """Calling flush() on a fresh parser with no buffered content returns []."""
    parser = ThinkTagParser()
    assert parser.flush() == []


# ---------------------------------------------------------------------------
# Additional edge-case: all emitted updates have non-empty text
# ---------------------------------------------------------------------------


def test_no_empty_text_updates_in_normal_flow() -> None:
    """Parser never emits a SessionUpdate whose text field is the empty string."""
    parser = ThinkTagParser()
    updates = collect_updates(
        parser,
        ["Some text ", "<think>", "deep thought", "</think>", " more text"],
    )
    for u in updates:
        assert str(u.data["text"]) != "", f"Got empty-text update: type={u.type}"


# ---------------------------------------------------------------------------
# Additional edge-case: tag spanning three or more chunks
# ---------------------------------------------------------------------------


def test_open_tag_spanning_three_chunks() -> None:
    """<think> tag fragments across three chunks are assembled correctly."""
    parser = ThinkTagParser()
    updates: list[SessionUpdate] = []
    updates.extend(parser.feed("<"))
    updates.extend(parser.feed("thi"))
    updates.extend(parser.feed("nk>inside"))
    updates.extend(parser.flush())

    assert "inside" in "".join(_thinking_texts(updates))
    for u in updates:
        assert "<think>" not in str(u.data["text"])
