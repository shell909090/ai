"""Embedding model wrapper: local (sentence-transformers) or OpenAI-compatible API."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps sentence-transformers (local) or OpenAI embeddings API for batch text embedding."""

    def __init__(
        self,
        model_name: str,
        backend: str = "local",
        api_base: str = "",
        api_key: str = "",
    ) -> None:
        self._model_name = model_name
        self._backend = backend
        self._dim: int | None = None

        if backend == "local":
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

            logger.debug("Loading local embedding model: %s", model_name)
            self._model = SentenceTransformer(model_name)
            self._dim = self._model.get_sentence_embedding_dimension()

        elif backend == "openai":
            try:
                from openai import OpenAI  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ImportError(
                    "openai package is not installed. Install it with: pip install elocate[openai]"
                ) from exc

            logger.debug("Using OpenAI-compatible embedding API: %s / %s", api_base, model_name)
            self._client = OpenAI(
                base_url=api_base or None,
                api_key=api_key or "none",
            )

        else:
            raise ValueError(f"Unknown embedder backend: {backend!r}. Use 'local' or 'openai'.")

    def embed(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into embedding vectors, shape (N, dim)."""
        if self._backend == "local":
            return self._model.encode(texts, convert_to_numpy=True)  # type: ignore[return-value]

        # openai backend
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
        # openai backend: probe dimension with a dummy call
        self.embed([""])
        assert self._dim is not None
        return self._dim
