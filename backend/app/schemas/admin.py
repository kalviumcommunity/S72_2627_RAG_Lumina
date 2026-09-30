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
