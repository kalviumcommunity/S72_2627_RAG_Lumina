from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.models.enums import ConflictStatus
from app.schemas.base import APIModel
from app.schemas.document import BranchOut, DepartmentOut, UserOut


class CountItem(APIModel):
    label: str
    count: int


class StaleDoc(APIModel):
    document_id: uuid.UUID
    doc_code: str
    title: str
    version: str
    review_due: date
    days_overdue: int


class DailyPoint(APIModel):
    day: date
    questions: int
    abstained: int


class StatsOut(APIModel):
    window_days: int
    total_questions: int
    answered: int
    partial: int
    abstained: int
    abstention_rate: float
    route_counts: dict[str, int]
    abstain_reasons: dict[str, int]
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    top_questions: list[CountItem]
    unanswered_questions: list[CountItem]
    top_documents: list[CountItem]
    stale_documents: list[StaleDoc]
    open_conflicts: int
    open_feedback: int
    pending_supersessions: int
    documents_awaiting_approval: int
    daily: list[DailyPoint] = Field(default_factory=list)


class ConflictSideOut(APIModel):
    chunk_id: uuid.UUID
    doc_code: str
    title: str
    version: str
    section_path: str
    text: str
    effective_from: date


class ConflictAdminOut(APIModel):
    id: uuid.UUID
    description: str
    detected_by: str
    status: ConflictStatus
    confidence: float | None
    created_at: datetime
    owner: str | None
    resolution_note: str | None
    a: ConflictSideOut
    b: ConflictSideOut


class ConflictPatch(APIModel):
    status: ConflictStatus
    resolution_note: str | None = Field(default=None, max_length=2000)


class AuditEventOut(APIModel):
    seq: int
    created_at: datetime
    actor: str | None
    action: str
    entity_type: str
    entity_id: str | None
    payload: dict[str, Any]
    hash: str
    prev_hash: str


class AuditVerifyOut(APIModel):
    ok: bool
    events_checked: int
    first_bad_seq: int | None = None
    reason: str | None = None


class ReferenceData(APIModel):
    branches: list[BranchOut]
    departments: list[DepartmentOut]
    users: list[UserOut]
    doc_types: list[str]


class ContactAdminOut(APIModel):
    id: uuid.UUID
    role_label: str
    branch_id: uuid.UUID | None
    department_id: uuid.UUID | None
    phone_ext: str | None
    phone: str | None
    pager: str | None
    notes: str | None
    escalation_for: list[str]


# --- admin overview (one page: AI usage, users, documents, amendments, conflicts, feedback) -------


class LLMTaskUsage(APIModel):
    task: str
    calls: int
    failures: int
    timeouts: int
    avg_ms: float | None


class AIConfigOut(APIModel):
    llm_provider: str
    llm_model: str | None
    reasoning_level: str | None  # Gemini thinking level / Claude effort
    embedding_model: str
    reranker_model: str
    pii_engine: str
    verifier_mode: str
    verifier_threshold: float
    min_relevance: float
    prompt_versions: dict[str, str]


class DroppedClaim(APIModel):
    claim: str
    issue: str | None


class AIDecision(APIModel):
    """One question and how the pipeline handled it (the system's "reasoning trace")."""

    query_id: uuid.UUID
    created_at: datetime
    user: str | None
    question: str  # redacted
    pii_redacted: bool
    route: str
    route_reason: str | None
    route_source: str | None  # rules | llm | llm+rules
    outcome: str | None
    abstain_reason: str | None
    generation_mode: str | None  # llm | extractive
    judge: str | None
    claims: int
    supported: int
    dropped: list[DroppedClaim] = Field(default_factory=list)
    cited: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    expansions: list[str] = Field(default_factory=list)
    latency_ms: int
    timings_ms: dict[str, int] = Field(default_factory=dict)


class AIUsageOut(APIModel):
    config: AIConfigOut
    questions: int
    pii_redacted: int
    generation_modes: dict[str, int]
    route_sources: dict[str, int]
    judges: dict[str, int]
    claims_checked: int
    claims_supported: int
    avg_stage_ms: dict[str, float]
    llm_calls: list[LLMTaskUsage]  # since the API process started
    recent: list[AIDecision]


class UserUsage(APIModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    branch: str | None
    questions: int
    answered: int
    partial: int
    abstained: int
    refused_high_risk: int
    feedback_given: int
    uploads: int
    approvals: int
    reviews: int  # amendments / conflicts / feedback handled
    last_active: datetime | None


class DocumentRow(APIModel):
    id: uuid.UUID
    doc_code: str
    title: str
    doc_type: str
    department: str | None
    owner: str | None
    current_version: str | None
    effective_from: date | None
    versions: int
    drafts: int
    review_due: date | None
    review_overdue: bool


class AmendmentRow(APIModel):
    id: uuid.UUID
    source: str  # "C-2026-09 v1"
    source_status: str
    target: str  # "P-ICU-07 §4.2"
    effective_from: date
    confirmed: bool
    suggested: bool
    evidence: str | None


class ConflictRow(APIModel):
    id: uuid.UUID
    a: str
    b: str
    description: str
    status: str
    detected_by: str
    owner: str | None
    created_at: datetime


class FeedbackRow(APIModel):
    id: uuid.UUID
    created_at: datetime
    kind: str
    status: str
    reporter: str | None
    routed_to: str | None
    question: str
    comment: str | None


class OverviewOut(APIModel):
    window_days: int
    ai: AIUsageOut
    users: list[UserUsage]
    documents: list[DocumentRow]
    amendments: list[AmendmentRow]
    conflicts: list[ConflictRow]
    feedback: list[FeedbackRow]
