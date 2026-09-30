"""Route answer feedback to the owner of the document it cited (or an admin if nothing was cited)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion
from app.models.enums import FeedbackKind, Role
from app.models.query_log import AnswerLog, Citation
from app.models.user import User


async def route_feedback(session: AsyncSession, answer: AnswerLog, kind: FeedbackKind) -> uuid.UUID | None:
    if kind == FeedbackKind.helpful:
        return None
    owner = (
        await session.execute(
            select(Document.owner_user_id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(Citation, Citation.version_id == DocumentVersion.id)
            .where(Citation.answer_id == answer.id, Document.owner_user_id.is_not(None))
            .order_by(Citation.marker)
            .limit(1)
        )
    ).scalar_one_or_none()
    if owner:
        return owner
    admin = (
        await session.execute(
            select(User.id).where(User.role == Role.admin, User.is_active.is_(True)).order_by(User.email).limit(1)
        )
    ).scalar_one_or_none()
    return admin
