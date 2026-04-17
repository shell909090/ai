"""Embedding model wrapper for text-to-vector conversion."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps sentence-transformers for batch text embedding."""

    def __init__(self, model_name: str) -> None:
        # deferred import to avoid slow startup when not needed
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        logger.debug("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into embedding vectors."""
        return self._model.encode(texts, convert_to_numpy=True)  # type: ignore[return-value]

    @property
    def dim(self) -> int:
        """Embedding vector dimension."""
        return self._model.get_sentence_embedding_dimension()  # type: ignore[return-value]
