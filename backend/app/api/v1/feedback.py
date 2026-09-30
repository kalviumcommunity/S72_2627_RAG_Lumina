from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import AuthorUser, CurrentUser, DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import has_role
from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion
from app.models.enums import Role
from app.models.feedback import Feedback
from app.models.query_log import AnswerLog, Citation, QueryLog
from app.models.user import User
from app.schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackPatch
from app.services import audit
from app.services.feedback import route_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


async def _out(session: DbSession, fb: Feedback) -> FeedbackOut:
    answer = await session.get(AnswerLog, fb.answer_id)
    assert answer is not None
    query = await session.get(QueryLog, answer.query_id)
    assert query is not None
    cited = (
        await session.execute(
            select(Document.doc_code, Chunk.section_path)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .join(Citation, Citation.version_id == DocumentVersion.id)
            .join(Chunk, Chunk.id == Citation.chunk_id)
            .where(Citation.answer_id == answer.id)
            .order_by(Citation.marker)
        )
    ).all()
    reporter = await session.get(User, fb.user_id) if fb.user_id else None
    routed = await session.get(User, fb.routed_to_user_id) if fb.routed_to_user_id else None
    return FeedbackOut(
        id=fb.id,
        query_id=query.id,
        kind=fb.kind,
        comment=fb.comment,
        status=fb.status,
        created_at=fb.created_at,
        question=query.redacted_question,
        answer=answer.answer_text,
        outcome=str(answer.outcome),
        cited=[f"{code} §{path}" for code, path in cited],
        reporter=reporter.display_name if reporter else None,
        routed_to=routed.display_name if routed else None,
        resolution_note=fb.resolution_note,
    )


@router.post("", response_model=FeedbackOut, status_code=201)
async def create_feedback(body: FeedbackCreate, user: CurrentUser, session: DbSession) -> FeedbackOut:
    query = await session.get(QueryLog, body.query_id)
    if query is None or query.answer is None:
        raise NotFoundError("Answer not found")
    if query.user_id != user.id and not has_role(user.role, Role.admin):
        raise ForbiddenError("You can only give feedback on your own answers")
    routed_to = await route_feedback(session, query.answer, body.kind)
    fb = Feedback(
        answer_id=query.answer.id,
        user_id=user.id,
        kind=body.kind,
        comment=(body.comment or None),
        routed_to_user_id=routed_to,
    )
    session.add(fb)
    await session.flush()
    await audit.record(
        session,
        action="feedback.created",
        entity_type="feedback",
        entity_id=fb.id,
        actor_user_id=user.id,
        payload={
            "kind": body.kind.value,
            "query_id": str(query.id),
            "routed_to": str(routed_to) if routed_to else None,
        },
    )
    await session.commit()
    return await _out(session, fb)


@router.get("/inbox", response_model=list[FeedbackOut])
async def inbox(user: AuthorUser, session: DbSession, include_resolved: bool = False) -> list[FeedbackOut]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).limit(200)
    if not has_role(user.role, Role.admin):
        stmt = stmt.where(Feedback.routed_to_user_id == user.id)
    if not include_resolved:
        stmt = stmt.where(Feedback.status != "resolved")
    stmt = stmt.where(Feedback.kind != "helpful")
    return [await _out(session, fb) for fb in (await session.execute(stmt)).scalars()]


@router.patch("/{feedback_id}", response_model=FeedbackOut)
async def update_feedback(
    feedback_id: uuid.UUID, body: FeedbackPatch, user: AuthorUser, session: DbSession
) -> FeedbackOut:
    fb = await session.get(Feedback, feedback_id)
    if fb is None:
        raise NotFoundError("Feedback not found")
    if fb.routed_to_user_id != user.id and not has_role(user.role, Role.admin):
        raise ForbiddenError("This feedback is routed to someone else")
    fb.status = body.status
    fb.resolution_note = body.resolution_note
    await audit.record(
        session,
        action="feedback.updated",
        entity_type="feedback",
        entity_id=fb.id,
        actor_user_id=user.id,
        payload={"status": body.status.value},
    )
    await session.commit()
    return await _out(session, fb)
