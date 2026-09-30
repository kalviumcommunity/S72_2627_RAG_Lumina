"""Query request/response schemas (mirrored by frontend/src/lib/types.ts via OpenAPI)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.models.enums import AnswerOutcome, QueryRoute
from app.schemas.base import APIModel

DISCLAIMER = "Supports, does not replace, clinical judgement."


class QueryRequest(APIModel):
    question: str = Field(min_length=2, max_length=1000)
    branch_id: uuid.UUID | None = None


class DocRef(APIModel):
    doc_code: str
    section_path: str | None = None


class CitationOut(APIModel):
    marker: str
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    title: str
    doc_type: str
    version: str
    section_path: str
    heading: str
    page: int
    effective_from: date
    supersedes: DocRef | None = None
    amends: list[DocRef] = Field(default_factory=list)
    snippet: str
    supported: bool
    support_score: float | None = None
    branch_specific: bool = False


class QuickValue(APIModel):
    label: str
    value: str
    source: str


class SourceCard(APIModel):
    marker: str
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    doc_code: str
    title: str
    doc_type: str
    version: str
    section_path: str
    heading: str
    page: int
    effective_from: date
    snippet: str
    relevance: float
    amends: list[DocRef] = Field(default_factory=list)
    branch_specific: bool = False


class ConflictSide(APIModel):
    marker: str | None = None
    chunk_id: uuid.UUID
    doc_code: str
    title: str
    version: str
    section_path: str
    effective_from: date
    snippet: str


class ConflictOut(APIModel):
    id: uuid.UUID | None = None
    description: str
    a: ConflictSide
    b: ConflictSide
    newer: Literal["a", "b"] | None = None
    status: str = "open"
    detected_by: str = "query"
    flagged_to_owner: bool = False


class ContactOut(APIModel):
    id: uuid.UUID
    role_label: str
    phone_ext: str | None = None
    phone: str | None = None
    pager: str | None = None
    notes: str | None = None


class EscalationOut(APIModel):
    reason: Literal["not_found", "high_risk", "out_of_scope", "clarify", "unavailable"]
    message: str
    contacts: list[ContactOut] = Field(default_factory=list)
    clarifying_question: str | None = None


class VerificationOut(APIModel):
    claims: int
    supported: int
    judge: str


class QueryResponse(APIModel):
    query_id: uuid.UUID
    route: QueryRoute
    outcome: AnswerOutcome
    answer: str | None
    citations: list[CitationOut] = Field(default_factory=list)
    quick_values: list[QuickValue] = Field(default_factory=list)
    conflicts: list[ConflictOut] = Field(default_factory=list)
    escalation: EscalationOut | None = None
    sources: list[SourceCard] = Field(default_factory=list)
    generation_mode: str | None = None
    verification: VerificationOut | None = None
    redacted_question: str
    pii_redacted: bool = False
    latency_ms: int
    # Per-stage milliseconds: route, retrieve (runs alongside route), generate, verify, total.
    timings_ms: dict[str, int] = Field(default_factory=dict)
    disclaimer: str = DISCLAIMER


class RouteEvent(APIModel):
    route: QueryRoute
    reason: str
    redacted_question: str
    pii_redacted: bool


class HistoryItem(APIModel):
    query_id: uuid.UUID
    question: str  # redacted
    route: QueryRoute
    outcome: AnswerOutcome | None
    created_at: datetime
