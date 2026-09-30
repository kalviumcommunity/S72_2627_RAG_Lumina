from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pydantic import Field

from app.models.enums import DocType, VersionStatus
from app.schemas.base import APIModel


class OutlineItem(APIModel):
    chunk_id: uuid.UUID
    section_path: str
    heading: str
    text: str
    is_table: bool
    page_start: int


class SupersededByRef(APIModel):
    doc_code: str
    title: str
    version: str
    version_id: uuid.UUID
    section_path: str | None
    effective_from: date


class AmendsRef(APIModel):
    doc_code: str
    section_path: str | None = None


class SourceOut(APIModel):
    chunk_id: uuid.UUID
    version_id: uuid.UUID
    document_id: uuid.UUID
    doc_code: str
    title: str
    doc_type: DocType
    version: str
    status: VersionStatus
    is_current: bool
    effective_from: date
    review_due: date | None
    section_path: str
    covered_paths: list[str]
    heading: str
    text: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    bbox: dict[str, Any] | None
    is_table: bool
    mime_type: str
    file_url: str
    ocr_min_confidence: float | None = None
    neighbours: dict[str, uuid.UUID | None] = Field(default_factory=dict)
    outline: list[OutlineItem] = Field(default_factory=list)
    superseded_by: list[SupersededByRef] = Field(default_factory=list)
    amends: list[AmendsRef] = Field(default_factory=list)
    newer_version: SupersededByRef | None = None
