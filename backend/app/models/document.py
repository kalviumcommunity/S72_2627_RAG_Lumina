from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.branch import Branch
from app.models.department import Department
from app.models.enums import DocType, IngestStatus, VersionStatus

document_branches = Table(
    "document_branches",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", ForeignKey("branches.id", ondelete="CASCADE"), primary_key=True),
)


class Document(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "documents"

    doc_code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType, native_enum=False, length=30, name="doc_type"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    applies_to_all_branches: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    department: Mapped[Department | None] = relationship(lazy="joined")
    branches: Mapped[list[Branch]] = relationship(secondary=document_branches, lazy="selectin")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", lazy="selectin", order_by="DocumentVersion.effective_from"
    )


class DocumentVersion(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_label", name="uq_document_versions_doc_label"),
        Index("ix_document_versions_status_effective", "status", "effective_from"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_label: Mapped[str] = mapped_column(String(40))
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, native_enum=False, length=20, name="version_status"),
        default=VersionStatus.draft,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[date] = mapped_column(Date)
    review_due: Mapped[date | None] = mapped_column(Date)
    change_summary: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)

    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, native_enum=False, length=20, name="ingest_status"),
        default=IngestStatus.pending,
    )
    ingest_error: Mapped[str | None] = mapped_column(Text)
    parser: Mapped[str | None] = mapped_column(String(40))
    page_count: Mapped[int | None]
    ocr_min_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_page_confidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ocr_acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ocr_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_warnings: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")

    document: Mapped[Document] = relationship(back_populates="versions", lazy="joined")

    @property
    def needs_ocr_acknowledgement(self) -> bool:
        return (
            self.ocr_min_confidence is not None
            and self.ocr_acknowledged_at is None
            and any(isinstance(w, dict) and w.get("code") == "ocr_low_confidence" for w in self.parse_warnings or [])
        )
