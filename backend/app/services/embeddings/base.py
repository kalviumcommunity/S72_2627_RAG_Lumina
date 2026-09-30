"""Embedding provider protocol plus a deterministic hashing embedder for tests and CI."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")


class EmbeddingProvider(Protocol):
    model_id: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashEmbeddingProvider:
    """Bag-of-words (unigram + bigram) feature hashing, L2-normalised.

    Not semantic, but deterministic, dependency-free and lexically meaningful — enough to test
    the retrieval plumbing without downloading a model.
    """

    model_id = "hash-bow-v1"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = tokenize(text)
        features = tokens + [f"{a} {b}" for a, b in itertools.pairwise(tokens)]
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
