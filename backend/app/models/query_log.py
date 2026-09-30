from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import AnswerOutcome, QueryRoute


class QueryLog(UUIDPrimaryKey, Timestamps, Base):
    """One row per question. Only the *redacted* question is ever stored."""

    __tablename__ = "query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    redacted_question: Mapped[str] = mapped_column(Text)
    pii_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    route: Mapped[QueryRoute] = mapped_column(Enum(QueryRoute, native_enum=False, length=20, name="route"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(120))
    retrieval: Mapped[list[Any] | None] = mapped_column(JSONB)

    answer: Mapped[AnswerLog | None] = relationship(back_populates="query", lazy="selectin", uselist=False)


class AnswerLog(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "answer_logs"

    query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_logs.id", ondelete="CASCADE"), unique=True)
    answer_text: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[AnswerOutcome] = mapped_column(Enum(AnswerOutcome, native_enum=False, length=20, name="outcome"))
    abstain_reason: Mapped[str | None] = mapped_column(String(40))
    generation_mode: Mapped[str | None] = mapped_column(String(20))
    verifier_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    conflicts: Mapped[list[Any] | None] = mapped_column(JSONB)
    quick_values: Mapped[list[Any] | None] = mapped_column(JSONB)

    query: Mapped[QueryLog] = relationship(back_populates="answer", lazy="joined")
    citations: Mapped[list[Citation]] = relationship(back_populates="answer", lazy="selectin")


class Citation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "citations"

    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answer_logs.id", ondelete="CASCADE"))
    marker: Mapped[str] = mapped_column(String(10))
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id"))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"))
    claim_text: Mapped[str | None] = mapped_column(Text)
    supported: Mapped[bool] = mapped_column(Boolean, default=False)
    support_score: Mapped[float | None] = mapped_column(Float)

    answer: Mapped[AnswerLog] = relationship(back_populates="citations")
