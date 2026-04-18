"""Tests for the Embedder module (mock SentenceTransformer)."""

from unittest.mock import MagicMock, patch

import numpy as np


def _make_embedder(dim: int = 64) -> "object":
    from elocate.embedder import Embedder

    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = dim
    mock_model.encode.side_effect = lambda texts, **_: np.ones((len(texts), dim), dtype=np.float32)

    embedder = Embedder.__new__(Embedder)
    embedder._model = mock_model
    return embedder


def test_embed_returns_correct_shape() -> None:
    embedder = _make_embedder(dim=64)
    result = embedder.embed(["hello", "world", "foo"])  # type: ignore[attr-defined]
    assert result.shape == (3, 64)


def test_embed_returns_float32() -> None:
    embedder = _make_embedder(dim=32)
    result = embedder.embed(["test"])  # type: ignore[attr-defined]
    assert result.dtype == np.float32


def test_dim_property() -> None:
    embedder = _make_embedder(dim=128)
    assert embedder.dim == 128  # type: ignore[attr-defined]


def test_embed_single_text() -> None:
    embedder = _make_embedder(dim=16)
    result = embedder.embed(["single"])  # type: ignore[attr-defined]
    assert result.shape == (1, 16)


def test_embedder_loads_model_on_init() -> None:
    from elocate.embedder import Embedder

    mock_st = MagicMock()
    mock_instance = MagicMock()
    mock_instance.get_sentence_embedding_dimension.return_value = 8
    mock_st.return_value = mock_instance

    # SentenceTransformer is imported inside __init__, so patch the source module
    with patch.dict(
        "sys.modules", {"sentence_transformers": MagicMock(SentenceTransformer=mock_st)}
    ):
        Embedder("my-model")
    mock_st.assert_called_once_with("my-model")
