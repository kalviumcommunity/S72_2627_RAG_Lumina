from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RateLimitedUser, ServicesDep
from app.core.config import get_settings
from app.core.errors import ValidationFailedError
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.models.query_log import QueryLog
from app.models.user import User
from app.schemas.query import HistoryItem, QueryRequest, QueryResponse
from app.services.orchestrator import Orchestrator
from app.services.registry import Services

router = APIRouter(prefix="/query", tags=["query"])
log = get_logger(__name__)


def _check_length(question: str) -> str:
    question = question.strip()
    if len(question) < 2 or len(question) > get_settings().max_question_chars:
        raise ValidationFailedError(f"Question must be 2–{get_settings().max_question_chars} characters")
    return question


@router.post("", response_model=QueryResponse)
async def ask(body: QueryRequest, user: RateLimitedUser, session: DbSession, services: ServicesDep) -> QueryResponse:
    return await Orchestrator(services).answer(session, _check_length(body.question), user, body.branch_id)


async def _sse(
    request: Request, services: Services, question: str, user: User, branch_id: uuid.UUID | None
) -> AsyncIterator[str]:
    # The session lives inside the generator so it spans the whole stream.
    async with get_sessionmaker()() as session:
        try:
            async for event in Orchestrator(services).run(session, question, user, branch_id):
                if await request.is_disconnected():
                    log.info("sse_client_disconnected")
                    return
                yield f"event: {event.event}\ndata: {json.dumps(event.data, separators=(',', ':'))}\n\n"
        except Exception as exc:
            log.error("sse_query_failed", error_type=type(exc).__name__)
            payload = {"code": "internal_error", "message": "The answer could not be produced safely."}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"


def _stream(
    request: Request, services: Services, question: str, user: User, branch_id: uuid.UUID | None
) -> StreamingResponse:
    return StreamingResponse(
        _sse(request, services, _check_length(question), user, branch_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/stream", response_class=StreamingResponse)
async def ask_stream_post(
    body: QueryRequest, request: Request, user: RateLimitedUser, services: ServicesDep
) -> StreamingResponse:
    """Preferred streaming form: the question travels in the body, never in a URL."""
    return _stream(request, services, body.question, user, body.branch_id)


@router.get("/stream", response_class=StreamingResponse)
async def ask_stream_get(
    request: Request,
    user: RateLimitedUser,
    services: ServicesDep,
    q: Annotated[str, Query(min_length=2, max_length=1000)],
    branch_id: uuid.UUID | None = None,
) -> StreamingResponse:
    """SSE over GET (spec compatibility). Access logs record the path only, never the query string."""
    return _stream(request, services, q, user, branch_id)


@router.get("/history", response_model=list[HistoryItem])
async def history(user: CurrentUser, session: DbSession, limit: int = 20) -> list[HistoryItem]:
    rows = await session.execute(
        select(QueryLog).where(QueryLog.user_id == user.id).order_by(QueryLog.created_at.desc()).limit(min(limit, 50))
    )
    return [
        HistoryItem(
            query_id=q.id,
            question=q.redacted_question,
            route=q.route,
            outcome=q.answer.outcome if q.answer else None,
            created_at=q.created_at,
        )
        for q in rows.scalars()
    ]
