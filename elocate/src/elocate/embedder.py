"""Embedding model wrapper: OpenAI-compatible API."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps an OpenAI-compatible embeddings API for batch text embedding."""

    def __init__(
        self,
        model_name: str,
        api_base: str = "",
        api_key: str = "",
    ) -> None:
        from openai import OpenAI

        self._model_name = model_name
        self._dim: int | None = None
        logger.debug("Using OpenAI-compatible embedding API: %s / %s", api_base, model_name)
        self._client = OpenAI(
            base_url=api_base or None,
            api_key=api_key or "none",
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into embedding vectors, shape (N, dim)."""
        response = self._client.embeddings.create(model=self._model_name, input=texts)
        vectors = [item.embedding for item in response.data]
        arr = np.array(vectors, dtype=np.float32)
        if self._dim is None:
            self._dim = arr.shape[1]
        return arr

    @property
    def dim(self) -> int:
        """Embedding vector dimension."""
        if self._dim is not None:
            return self._dim
        # empty strings are rejected by many providers, use a real token
        self.embed(["dim-probe"])
        assert self._dim is not None
        return self._dim
