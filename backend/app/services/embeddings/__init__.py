"""Embedding provider factory."""

from __future__ import annotations

from app.core.config import Settings
from app.services.embeddings.base import EmbeddingProvider, HashEmbeddingProvider


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "hash":
        return HashEmbeddingProvider(settings.embedding_dim)
    from app.services.embeddings.sentence_transformers_provider import SentenceTransformerEmbeddingProvider

    return SentenceTransformerEmbeddingProvider(
        settings.embedding_model, settings.embedding_dim, settings.embedding_batch_size, settings.model_device
    )


__all__ = ["EmbeddingProvider", "HashEmbeddingProvider", "build_embedder"]
