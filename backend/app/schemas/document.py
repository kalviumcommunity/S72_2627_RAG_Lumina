from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import ConfigDict, Field

from app.models.enums import DocType, IngestStatus, Role, VersionStatus
from app.schemas.base import APIModel


class ORM(APIModel):
    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)


class BranchOut(ORM):
    id: uuid.UUID
    name: str
    code: str


class DepartmentOut(ORM):
    id: uuid.UUID
    name: str
    code: str


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    branch: BranchOut | None = None
    department: DepartmentOut | None = None


class VersionOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    version_label: str
    status: VersionStatus
    effective_from: date
    review_due: date | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    retired_at: datetime | None = None
    change_summary: str | None = None
    original_filename: str
    mime_type: str
    file_sha256: str
    ingest_status: IngestStatus
    ingest_error: str | None = None
    parser: str | None = None
    page_count: int | None = None
    ocr_min_confidence: float | None = None
    ocr_page_confidence: dict[str, Any] | None = None
    ocr_acknowledged_at: datetime | None = None
    parse_warnings: list[Any] = Field(default_factory=list)
    needs_ocr_acknowledgement: bool = False
    is_current: bool = False
    chunk_count: int = 0
    created_at: datetime


class SupersessionOut(APIModel):
    id: uuid.UUID
    source_version_id: uuid.UUID
    source_doc_code: str
    source_version_label: str
    source_status: VersionStatus
    target_document_id: uuid.UUID
    target_doc_code: str
    target_section_path: str | None
    effective_from: date
    note: str | None = None
    evidence: str | None = None
    suggested: bool
    confirmed: bool
    confirmed_at: datetime | None = None
    # Clauses of the target's current version this link hides (merged chunks are hidden whole).
    hides_sections: list[str] = Field(default_factory=list)


class DocumentOut(APIModel):
    id: uuid.UUID
    doc_code: str
    title: str
    doc_type: DocType
    department: DepartmentOut | None = None
    owner: UserOut | None = None
    applies_to_all_branches: bool
    branches: list[BranchOut] = Field(default_factory=list)
    versions: list[VersionOut] = Field(default_factory=list)
    current_version_id: uuid.UUID | None = None
    review_overdue: bool = False
    next_review_due: date | None = None


class DocumentDetail(DocumentOut):
    supersessions_out: list[SupersessionOut] = Field(default_factory=list)  # links this doc's versions create
    supersessions_in: list[SupersessionOut] = Field(default_factory=list)  # links that amend this doc


class ChunkOut(ORM):
    id: uuid.UUID
    ordinal: int
    section_path: str
    covered_paths: list[str]
    heading: str
    text: str
    page_start: int
    page_end: int
    is_table: bool
    token_count: int
    bbox: dict[str, Any] | None = None


class UploadResult(APIModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    ingest_status: IngestStatus
    created_document: bool
    job: str


class SupersessionCreate(APIModel):
    source_version_id: uuid.UUID
    target_document_id: uuid.UUID
    target_section_path: str | None = Field(default=None, max_length=80)
    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    confirmed: bool = False


class SupersessionPatch(APIModel):
    confirmed: bool | None = None
    target_section_path: str | None = Field(default=None, max_length=80)
    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class ApproveRequest(APIModel):
    confirm_suggested_supersessions: bool = False


class ActionResult(APIModel):
    ok: bool = True
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExtractedMetadataOut(APIModel):
    doc_code: str | None = None
    version_label: str | None = None
    effective_from: date | None = None
    review_due: date | None = None
    title: str | None = None
