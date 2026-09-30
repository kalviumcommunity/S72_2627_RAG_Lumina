from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Contact(UUIDPrimaryKey, Timestamps, Base):
    """Escalation directory entry. branch_id NULL = applies network-wide."""

    __tablename__ = "contacts"

    role_label: Mapped[str] = mapped_column(String(200))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    phone_ext: Mapped[str | None] = mapped_column(String(40))
    phone: Mapped[str | None] = mapped_column(String(40))  # dialable number for tel: links
    pager: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    # Which abstention reasons this contact is relevant for (high_risk, not_found, ...).
    escalation_for: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)
