from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import FeedbackKind, FeedbackStatus


class Feedback(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "feedback"

    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answer_logs.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[FeedbackKind] = mapped_column(Enum(FeedbackKind, native_enum=False, length=20, name="feedback_kind"))
    comment: Mapped[str | None] = mapped_column(Text)
    routed_to_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, native_enum=False, length=20, name="feedback_status"),
        default=FeedbackStatus.open,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
