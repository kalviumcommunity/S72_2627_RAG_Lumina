from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import FeedbackKind, FeedbackStatus
from app.schemas.base import APIModel


class FeedbackCreate(APIModel):
    query_id: uuid.UUID
    kind: FeedbackKind
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(APIModel):
    id: uuid.UUID
    query_id: uuid.UUID
    kind: FeedbackKind
    comment: str | None
    status: FeedbackStatus
    created_at: datetime
    question: str  # redacted
    answer: str | None
    outcome: str
    cited: list[str] = Field(default_factory=list)
    reporter: str | None = None
    routed_to: str | None = None
    resolution_note: str | None = None


class FeedbackPatch(APIModel):
    status: FeedbackStatus
    resolution_note: str | None = Field(default=None, max_length=2000)
