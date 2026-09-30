"""Cross-encoder re-ranking (BAAI/bge-reranker-base) with a lexical fallback for tests."""

from __future__ import annotations

import contextlib
import math
import threading
from typing import Any, Protocol

from app.services.textutil import stemmed_words


class Reranker(Protocol):
    model_id: str

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance in [0, 1] per passage."""
        ...


def resolve_device(preference: str) -> str:
    if preference == "cpu":
        return "cpu"
    with contextlib.suppress(Exception):  # a broken CUDA install must never stop the API
        import torch

        if torch.cuda.is_available():
            return "cuda"
    return "cpu"


class CrossEncoderReranker:
    def __init__(self, model_name: str, max_length: int = 320, device: str = "auto") -> None:
        self.model_id = model_name
        self._max_length = max_length
        self._device = device
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    device = resolve_device(self._device)
                    model = CrossEncoder(self.model_id, device=device, max_length=self._max_length)
                    if device == "cuda":
                        model.model.half()
                    self._model = model
        return self._model

    def warmup(self) -> None:
        self.score("warmup", ["warmup passage"])

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        raw = self._load().predict(
            [(query, p) for p in passages], batch_size=16, show_progress_bar=False, convert_to_numpy=True
        )
        values = [float(x) for x in raw]
        # sentence-transformers applies a sigmoid for single-label models; guard against raw logits.
        if any(v < 0.0 or v > 1.0 for v in values):
            values = [1.0 / (1.0 + math.exp(-v)) for v in values]
        return values


class LexicalReranker:
    """Stemmed content-word recall of the query in the passage (deterministic, for tests/CI)."""

    model_id = "lexical-overlap-v1"

    def score(self, query: str, passages: list[str]) -> list[float]:
        q = stemmed_words(query)
        if not q:
            return [0.0 for _ in passages]
        return [round(len(q & stemmed_words(p)) / len(q), 4) for p in passages]
