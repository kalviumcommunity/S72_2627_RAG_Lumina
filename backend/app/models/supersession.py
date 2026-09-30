from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.document import Document, DocumentVersion


class Supersession(UUIDPrimaryKey, Timestamps, Base):
    """`source_version` (the amending document) supersedes `target_document` (optionally one section)."""

    __tablename__ = "supersessions"

    source_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    target_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    target_section_path: Mapped[str | None] = mapped_column(String(80))  # NULL = whole document
    effective_from: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)  # the sentence that triggered a suggestion
    suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_version: Mapped[DocumentVersion] = relationship(lazy="joined")
    target_document: Mapped[Document] = relationship(lazy="joined")
