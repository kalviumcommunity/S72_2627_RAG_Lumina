"""String enums shared by models, schemas and services."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    clinician = "clinician"
    author = "author"
    approver = "approver"
    admin = "admin"


ROLE_RANK: dict[Role, int] = {Role.clinician: 0, Role.author: 1, Role.approver: 2, Role.admin: 3}


class DocType(StrEnum):
    protocol = "protocol"
    drug_guideline = "drug_guideline"
    circular = "circular"
    sop = "sop"
    external_reference = "external_reference"


class VersionStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    superseded = "superseded"
    retired = "retired"


class IngestStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ConflictStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class DetectedBy(StrEnum):
    ingest = "ingest"
    query = "query"
    user = "user"


class QueryRoute(StrEnum):
    answer = "answer"
    clarify = "clarify"
    out_of_scope = "out_of_scope"
    high_risk = "high_risk"


class AnswerOutcome(StrEnum):
    answered = "answered"
    abstained = "abstained"
    partial = "partial"


class FeedbackKind(StrEnum):
    wrong = "wrong"
    outdated = "outdated"
    unhelpful = "unhelpful"
    helpful = "helpful"


class FeedbackStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
