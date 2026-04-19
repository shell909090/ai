"""Tests for the Embedder module (mock backends)."""

from unittest.mock import MagicMock, patch

import numpy as np

# ------------------------------------------------------------------ openai backend


def _make_openai_embedder(dim: int = 64) -> "object":
    from elocate.embedder import Embedder

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * dim)]
    mock_client.embeddings.create.return_value = mock_response

    embedder = Embedder.__new__(Embedder)
    embedder._backend = "openai"
    embedder._model_name = "nomic-embed-text"
    embedder._client = mock_client
    embedder._dim = None
    return embedder


def test_openai_embed_returns_correct_shape() -> None:
    dim = 32
    embedder = _make_openai_embedder(dim=dim)

    mock_client = embedder._client  # type: ignore[attr-defined]
    mock_client.embeddings.create.return_value.data = [
        MagicMock(embedding=[0.1] * dim),
        MagicMock(embedding=[0.2] * dim),
    ]
    result = embedder.embed(["hello", "world"])  # type: ignore[attr-defined]
    assert result.shape == (2, dim)


def test_openai_embed_returns_float32() -> None:
    embedder = _make_openai_embedder(dim=16)
    result = embedder.embed(["test"])  # type: ignore[attr-defined]
    assert result.dtype == np.float32


def test_openai_dim_probed_on_first_access() -> None:
    embedder = _make_openai_embedder(dim=48)
    assert embedder._dim is None  # type: ignore[attr-defined]
    d = embedder.dim  # type: ignore[attr-defined]
    assert d == 48
    assert embedder._dim == 48  # type: ignore[attr-defined]


def test_openai_dim_probe_uses_nonempty_input() -> None:
    """B007: dim probe must not send empty string (rejected by many providers)."""
    embedder = _make_openai_embedder(dim=16)
    _ = embedder.dim  # type: ignore[attr-defined]
    call_args = embedder._client.embeddings.create.call_args  # type: ignore[attr-defined]
    texts_sent = (
        call_args.kwargs.get("input") or call_args.args[0]
        if call_args.args
        else call_args.kwargs.get("input")
    )
    # The probe input must be non-empty
    assert texts_sent and all(t for t in texts_sent)


def test_openai_dim_cached_after_first_embed() -> None:
    embedder = _make_openai_embedder(dim=24)
    embedder.embed(["x"])  # type: ignore[attr-defined]
    assert embedder._dim == 24  # type: ignore[attr-defined]
    # second call to dim should not invoke embed again
    call_count_before = embedder._client.embeddings.create.call_count  # type: ignore[attr-defined]
    _ = embedder.dim  # type: ignore[attr-defined]
    assert embedder._client.embeddings.create.call_count == call_count_before  # type: ignore[attr-defined]


def test_openai_backend_empty_api_key_uses_none() -> None:
    """Empty api_key should be replaced with 'none' for the OpenAI SDK."""
    from elocate.embedder import Embedder

    mock_openai_cls = MagicMock()
    mock_openai_cls.return_value = MagicMock()

    # OpenAI is imported inside __init__, so patch via sys.modules only
    with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
        Embedder("model", api_base="http://localhost:11434/v1", api_key="")

    _, kwargs = mock_openai_cls.call_args
    assert kwargs.get("api_key") == "none"


def test_embedder_init_creates_openai_client() -> None:
    """Embedder.__init__ should create an OpenAI client with given base_url and api_key."""
    from elocate.embedder import Embedder

    mock_openai_cls = MagicMock()
    mock_openai_cls.return_value = MagicMock()

    with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
        Embedder("nomic-embed-text", api_base="http://localhost:11434/v1", api_key="ollama")

    _, kwargs = mock_openai_cls.call_args
    assert kwargs.get("base_url") == "http://localhost:11434/v1"
    assert kwargs.get("api_key") == "ollama"
