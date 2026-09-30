"""Reciprocal Rank Fusion of keyword and vector result lists."""

from __future__ import annotations

import uuid
from collections.abc import Sequence


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[uuid.UUID]], *, k: int = 60, limit: int | None = None
) -> list[tuple[uuid.UUID, float]]:
    """score(d) = Σ 1 / (k + rank_i(d)), ranks starting at 1. Ties keep first-seen order."""
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    fused = sorted(scores.items(), key=lambda kv: -kv[1])
    return fused[:limit] if limit else fused
