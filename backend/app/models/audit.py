from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """Append-only, hash-chained audit trail.

    UPDATE / DELETE / TRUNCATE are blocked by database triggers (see the initial migration), and
    `hash = sha256(prev_hash + canonical_json(record))` lets `make audit-verify` detect tampering.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
