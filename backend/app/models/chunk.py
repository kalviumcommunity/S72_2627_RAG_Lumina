from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.document import DocumentVersion

EMBEDDING_DIM = get_settings().embedding_dim


class Chunk(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_version_ordinal", "version_id", "ordinal"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str] = mapped_column(String(80))
    # Every clause path this chunk covers (tiny sibling clauses are merged; (a)/(b) sub-clauses).
    covered_paths: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list)
    heading: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text)
    context_header: Mapped[str] = mapped_column(String(600), default="")
    page_start: Mapped[int] = mapped_column(Integer, default=1)
    page_end: Mapped[int] = mapped_column(Integer, default=1)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_table: Mapped[bool] = mapped_column(Boolean, default=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english'::regconfig, coalesce(context_header, '') || ' ' || coalesce(text, ''))",
            persisted=True,
        ),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    version: Mapped[DocumentVersion] = relationship(lazy="joined")
