"""Retrieval data types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Candidate:
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    title: str
    doc_type: str
    department_id: uuid.UUID | None
    version_label: str
    status: str
    effective_from: date
    approved_at: datetime | None
    section_path: str
    covered_paths: list[str]
    heading: str
    text: str
    page_start: int
    page_end: int
    is_table: bool
    applies_to_all_branches: bool
    branch_ids: list[uuid.UUID]
    is_current: bool = False
    is_superseded: bool = False
    # Sections this chunk's version amends: [{"doc_code", "document_id", "section_path"}]
    supersedes: list[dict[str, Any]] = field(default_factory=list)
    keyword_rank: int | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    best_window: str | None = None  # the part of the passage that matched best (MaxP)
    final_score: float = 0.0
    boosts: dict[str, float] = field(default_factory=dict)

    @property
    def rerank_text(self) -> str:
        return f"{self.title} — {self.heading}\n{self.text}"

    @property
    def label(self) -> str:
        return f"{self.doc_code} v{self.version_label} §{self.section_path}"


@dataclass
class RetrievalResult:
    query: str
    expanded_query: str
    expansions: list[tuple[str, str]]
    candidates: list[Candidate]  # final context, best first
    reranked: list[Candidate]  # top-N after re-ranking (superset of candidates)
    dropped_by_authority: int
    timings_ms: dict[str, float]
    key_terms: list[str] = field(default_factory=list)
    # Named entities in the question that no indexed document mentions → answer "not found".
    uncovered_terms: list[str] = field(default_factory=list)

    @property
    def top_relevance(self) -> float:
        """Best raw re-ranker score (boosts reorder results but never pass the relevance gate)."""
        return max((c.rerank_score for c in self.candidates), default=0.0)
