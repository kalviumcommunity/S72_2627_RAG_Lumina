from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.chunk import Chunk
from app.models.enums import ConflictStatus, DetectedBy


class Conflict(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conflicts"
    __table_args__ = (UniqueConstraint("chunk_a_id", "chunk_b_id", name="uq_conflicts_pair"),)

    chunk_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    chunk_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    detected_by: Mapped[DetectedBy] = mapped_column(Enum(DetectedBy, native_enum=False, length=20, name="detected_by"))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus, native_enum=False, length=20, name="conflict_status"),
        default=ConflictStatus.open,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunk_a: Mapped[Chunk] = relationship(foreign_keys=[chunk_a_id], lazy="joined")
    chunk_b: Mapped[Chunk] = relationship(foreign_keys=[chunk_b_id], lazy="joined")
