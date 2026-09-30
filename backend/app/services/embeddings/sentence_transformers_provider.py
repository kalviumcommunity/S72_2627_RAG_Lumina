"""Local sentence-transformers embeddings (default: intfloat/multilingual-e5-base, CPU)."""

from __future__ import annotations

import threading
from typing import Any


class SentenceTransformerEmbeddingProvider:
    """E5-family models expect "query: " / "passage: " prefixes; embeddings are normalised."""

    def __init__(self, model_name: str, dim: int, batch_size: int = 16, device: str = "auto") -> None:
        self.model_id = model_name
        self.dim = dim
        self._batch_size = batch_size
        self._device = device
        self._model: Any = None
        self._lock = threading.Lock()
        self._e5 = "e5" in model_name.lower()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    from app.services.retrieval.reranker import resolve_device

                    model = SentenceTransformer(self.model_id, device=resolve_device(self._device))
                    dim_fn = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
                    got = dim_fn()
                    if got != self.dim:
                        raise ValueError(f"{self.model_id} produces {got}-dim vectors; EMBEDDING_DIM={self.dim}")
                    self._model = model
        return self._model

    def warmup(self) -> None:
        self.embed_query("warmup")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(x) for x in row] for row in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = "passage: " if self._e5 else ""
        return self._encode([prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        prefix = "query: " if self._e5 else ""
        return self._encode([prefix + text])[0]
