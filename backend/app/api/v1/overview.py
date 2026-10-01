"""Admin overview: everything an administrator needs on one page.

AI usage (configuration, how answers were produced and verified, live LLM call counters and a
per-question decision trace), usage per user, and the state of documents, amendments, conflicts and
feedback. Read-only; the work queues themselves live on their own pages.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, DbSession, ServicesDep
from app.models.chunk import Chunk
from app.models.conflict import Conflict
from app.models.document import Document, DocumentVersion
from app.models.enums import VersionStatus
from app.models.feedback import Feedback
from app.models.query_log import AnswerLog, Citation, QueryLog
from app.models.supersession import Supersession
from app.models.user import User
from app.schemas.admin import (
    AIConfigOut,
    AIDecision,
    AIUsageOut,
    AmendmentRow,
    ConflictRow,
    DocumentRow,
    DroppedClaim,
    FeedbackRow,
    LLMTaskUsage,
    OverviewOut,
    UserUsage,
)
from app.services.ingestion.supersession import VersionInfo, current_version
from app.services.registry import Services

router = APIRouter(tags=["admin"])

RECENT_DECISIONS = 25
STAGES = ("route", "retrieve", "generate", "verify", "total")
LLM_TASKS = ("classify", "generate", "verify", "conflict")
REVIEW_ACTIONS = (
    "supersession.confirmed",
    "supersession.created",
    "supersession.updated",
    "supersession.rejected",
    "conflict.updated",
    "feedback.updated",
    "version.ocr_acknowledged",
    "version.retired",
)


@router.get("/admin/overview", response_model=OverviewOut)
async def overview(user: AdminUser, session: DbSession, services: ServicesDep, days: int = 30) -> OverviewOut:
    days = max(1, min(days, 365))
    since = datetime.now(UTC) - timedelta(days=days)
    users = {u.id: u for u in (await session.execute(select(User))).scalars()}
    return OverviewOut(
        window_days=days,
        ai=await _ai_usage(session, services, since, users),
        users=await _user_usage(session, since, users),
        documents=await _documents(session, services, users),
        amendments=await _amendments(session),
        conflicts=await _conflicts(session, users),
        feedback=await _feedback(session, users),
    )


def _name(users: dict[uuid.UUID, User], user_id: uuid.UUID | None) -> str | None:
    found = users.get(user_id) if user_id else None
    return found.display_name if found else None


# --- AI usage --------------------------------------------------------------------------------------


def _ai_config(services: Services) -> AIConfigOut:
    s = services.settings
    llm = services.llm
    levels = {"gemini": s.gemini_thinking_level or None, "anthropic": s.anthropic_effort}
    reasoning = levels.get(llm.name) if llm else None
    prompts = services.prompts
    return AIConfigOut(
        llm_provider=llm.name if llm else "none",
        llm_model=llm.model_id if llm else None,
        reasoning_level=reasoning,
        embedding_model=services.embedder.model_id,
        reranker_model=services.reranker.model_id,
        pii_engine=services.redactor.status,
        verifier_mode=s.verifier_mode,
        verifier_threshold=s.verifier_threshold,
        min_relevance=s.min_relevance,
        prompt_versions={p.name: p.version for p in (prompts.classifier, prompts.generator, prompts.verifier)},
    )


def _llm_calls(services: Services) -> list[LLMTaskUsage]:
    usage: dict[str, Any] = getattr(services.llm, "usage", None) or {}
    order = {task: i for i, task in enumerate(LLM_TASKS)}
    return [
        LLMTaskUsage(task=task, calls=u.calls, failures=u.failures, timeouts=u.timeouts, avg_ms=u.avg_ms)
        for task, u in sorted(usage.items(), key=lambda kv: order.get(kv[0], len(order)))
    ]


async def _ai_usage(
    session: AsyncSession, services: Services, since: datetime, users: dict[uuid.UUID, User]
) -> AIUsageOut:
    rows = (
        await session.execute(
            select(
                QueryLog.id,
                QueryLog.created_at,
                QueryLog.user_id,
                QueryLog.redacted_question,
                QueryLog.pii_redacted,
                QueryLog.route,
                QueryLog.latency_ms,
                QueryLog.trace,
                AnswerLog.id.label("answer_id"),
                AnswerLog.outcome,
                AnswerLog.abstain_reason,
                AnswerLog.generation_mode,
                AnswerLog.verifier_summary,
            )
            .outerjoin(AnswerLog, AnswerLog.query_id == QueryLog.id)
            .where(QueryLog.created_at >= since)
            .order_by(QueryLog.created_at.desc())
            .limit(5000)
        )
    ).all()

    modes: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    judges: Counter[str] = Counter()
    stage_totals: dict[str, list[float]] = defaultdict(list)
    claims = supported = redacted = 0
    for r in rows:
        trace = r.trace or {}
        summary = r.verifier_summary or {}
        modes[r.generation_mode or "not drafted"] += 1
        sources[str(trace.get("route_source") or "not recorded")] += 1
        if summary.get("judge"):
            judges[str(summary["judge"])] += 1
        claims += int(summary.get("claims") or 0)
        supported += int(summary.get("supported") or 0)
        redacted += bool(r.pii_redacted)
        for stage, ms in (trace.get("timings_ms") or {}).items():
            if stage in STAGES and isinstance(ms, int | float):
                stage_totals[stage].append(float(ms))

    recent = rows[:RECENT_DECISIONS]
    cited: dict[uuid.UUID, list[str]] = defaultdict(list)
    answer_ids = [r.answer_id for r in recent if r.answer_id]
    if answer_ids:
        for answer_id, code, path in await session.execute(
            select(Citation.answer_id, Document.doc_code, Chunk.section_path)
            .join(Chunk, Chunk.id == Citation.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == Citation.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Citation.answer_id.in_(answer_ids))
            .order_by(Citation.marker)
        ):
            cited[answer_id].append(f"{code} §{path}")

    decisions = []
    for r in recent:
        trace = r.trace or {}
        summary = r.verifier_summary or {}
        timings = trace.get("timings_ms") or {}
        decisions.append(
            AIDecision(
                query_id=r.id,
                created_at=r.created_at,
                user=_name(users, r.user_id),
                question=r.redacted_question,
                pii_redacted=r.pii_redacted,
                route=str(r.route),
                route_reason=trace.get("route_reason"),
                route_source=trace.get("route_source"),
                outcome=str(r.outcome) if r.outcome else None,
                abstain_reason=r.abstain_reason,
                generation_mode=r.generation_mode,
                judge=summary.get("judge"),
                claims=int(summary.get("claims") or 0),
                supported=int(summary.get("supported") or 0),
                dropped=[
                    DroppedClaim(claim=str(d.get("claim", "")), issue=d.get("issue"))
                    for d in summary.get("dropped") or []
                    if isinstance(d, dict)
                ],
                cited=cited.get(r.answer_id, []) if r.answer_id else [],
                key_terms=list(trace.get("key_terms") or []),
                expansions=list(trace.get("expansions") or []),
                latency_ms=r.latency_ms,
                timings_ms={k: int(v) for k, v in timings.items() if isinstance(v, int | float)},
            )
        )

    return AIUsageOut(
        config=_ai_config(services),
        questions=len(rows),
        pii_redacted=redacted,
        generation_modes=dict(modes),
        route_sources=dict(sources),
        judges=dict(judges),
        claims_checked=claims,
        claims_supported=supported,
        avg_stage_ms={stage: round(sum(v) / len(v), 1) for stage in STAGES if (v := stage_totals.get(stage))},
        llm_calls=_llm_calls(services),
        recent=decisions,
    )


# --- usage per user --------------------------------------------------------------------------------


async def _user_usage(session: AsyncSession, since: datetime, users: dict[uuid.UUID, User]) -> list[UserUsage]:
    params = {"since": since}
    questions = {
        row.id: row
        for row in await session.execute(
            text("""
        SELECT u.id,
               count(q.id) AS questions,
               count(q.id) FILTER (WHERE a.outcome = 'answered') AS answered,
               count(q.id) FILTER (WHERE a.outcome = 'partial') AS partial,
               count(q.id) FILTER (WHERE a.outcome = 'abstained') AS abstained,
               count(q.id) FILTER (WHERE q.route = 'high_risk') AS refused
        FROM users u
        LEFT JOIN query_logs q ON q.user_id = u.id AND q.created_at >= :since
        LEFT JOIN answer_logs a ON a.query_id = q.id
        GROUP BY u.id"""),
            params,
        )
    }
    feedback: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                text("SELECT user_id, count(*) FROM feedback WHERE created_at >= :since GROUP BY user_id"), params
            )
        ).all()
    )
    actions: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    last_active: dict[uuid.UUID, datetime] = {}
    for actor, action, count, latest in await session.execute(
        text("""
        SELECT actor_user_id, action, count(*), max(created_at) FROM audit_events
        WHERE created_at >= :since AND actor_user_id IS NOT NULL GROUP BY actor_user_id, action"""),
        params,
    ):
        actions[actor][action] += count
        last_active[actor] = max(latest, last_active.get(actor, latest))

    out = []
    for user_id, u in users.items():
        q = questions.get(user_id)
        done = actions.get(user_id, Counter())
        out.append(
            UserUsage(
                user_id=user_id,
                name=u.display_name,
                email=u.email,
                role=u.role.value,
                branch=u.branch.name if u.branch else None,
                questions=q.questions if q else 0,
                answered=q.answered if q else 0,
                partial=q.partial if q else 0,
                abstained=q.abstained if q else 0,
                refused_high_risk=q.refused if q else 0,
                feedback_given=feedback.get(user_id, 0),
                uploads=done["version.uploaded"],
                approvals=done["version.approved"],
                reviews=sum(done[a] for a in REVIEW_ACTIONS),
                last_active=last_active.get(user_id),
            )
        )
    return sorted(out, key=lambda x: (-x.questions, -(x.uploads + x.approvals + x.reviews), x.name))


# --- documents, amendments, conflicts, feedback ----------------------------------------------------


async def _documents(session: AsyncSession, services: Services, users: dict[uuid.UUID, User]) -> list[DocumentRow]:
    today = services.settings.today()
    out = []
    for doc in (await session.execute(select(Document).order_by(Document.doc_code))).unique().scalars():
        infos = [VersionInfo(v.id, v.document_id, v.status, v.effective_from, v.approved_at) for v in doc.versions]
        current = current_version(infos, today)
        current_row = next((v for v in doc.versions if current and v.id == current.id), None)
        reviews = [v.review_due for v in doc.versions if v.status == VersionStatus.approved and v.review_due]
        review_due = min(reviews) if reviews else None
        out.append(
            DocumentRow(
                id=doc.id,
                doc_code=doc.doc_code,
                title=doc.title,
                doc_type=doc.doc_type.value,
                department=doc.department.name if doc.department else None,
                owner=_name(users, doc.owner_user_id),
                current_version=current_row.version_label if current_row else None,
                effective_from=current_row.effective_from if current_row else None,
                versions=len(doc.versions),
                drafts=sum(v.status == VersionStatus.draft for v in doc.versions),
                review_due=review_due,
                review_overdue=bool(review_due and review_due < today),
            )
        )
    return out


async def _amendments(session: AsyncSession) -> list[AmendmentRow]:
    versions = {
        vid: (code, label, status)
        for vid, code, label, status in await session.execute(
            select(DocumentVersion.id, Document.doc_code, DocumentVersion.version_label, DocumentVersion.status).join(
                Document, Document.id == DocumentVersion.document_id
            )
        )
    }
    codes = dict((await session.execute(select(Document.id, Document.doc_code))).all())
    rows = await session.execute(
        select(
            Supersession.id,
            Supersession.source_version_id,
            Supersession.target_document_id,
            Supersession.target_section_path,
            Supersession.effective_from,
            Supersession.confirmed,
            Supersession.suggested,
            Supersession.evidence,
        ).order_by(Supersession.confirmed, Supersession.created_at.desc())
    )
    out = []
    for r in rows:
        code, label, status = versions.get(r.source_version_id, ("?", "?", "draft"))
        target = codes.get(r.target_document_id, "?")
        out.append(
            AmendmentRow(
                id=r.id,
                source=f"{code} v{label}",
                source_status=str(status),
                target=f"{target} §{r.target_section_path}" if r.target_section_path else f"{target} (whole document)",
                effective_from=r.effective_from,
                confirmed=r.confirmed,
                suggested=r.suggested,
                evidence=r.evidence,
            )
        )
    return out


async def _conflicts(session: AsyncSession, users: dict[uuid.UUID, User]) -> list[ConflictRow]:
    rows = (
        await session.execute(
            select(
                Conflict.id,
                Conflict.chunk_a_id,
                Conflict.chunk_b_id,
                Conflict.description,
                Conflict.status,
                Conflict.detected_by,
                Conflict.owner_user_id,
                Conflict.created_at,
            ).order_by(Conflict.created_at.desc())
        )
    ).all()
    chunk_ids = {cid for r in rows for cid in (r.chunk_a_id, r.chunk_b_id)}
    labels: dict[uuid.UUID, str] = {}
    if chunk_ids:
        for cid, code, label, path in await session.execute(
            select(Chunk.id, Document.doc_code, DocumentVersion.version_label, Chunk.section_path)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Chunk.id.in_(chunk_ids))
        ):
            labels[cid] = f"{code} v{label} §{path}"
    return [
        ConflictRow(
            id=r.id,
            a=labels.get(r.chunk_a_id, "?"),
            b=labels.get(r.chunk_b_id, "?"),
            description=r.description,
            status=str(r.status),
            detected_by=str(r.detected_by),
            owner=_name(users, r.owner_user_id),
            created_at=r.created_at,
        )
        # Open first, newest first within each status.
        for r in sorted(rows, key=lambda r: str(r.status) != "open")
    ]


async def _feedback(session: AsyncSession, users: dict[uuid.UUID, User]) -> list[FeedbackRow]:
    rows = await session.execute(
        select(Feedback, QueryLog.redacted_question)
        .join(AnswerLog, AnswerLog.id == Feedback.answer_id)
        .join(QueryLog, QueryLog.id == AnswerLog.query_id)
        .order_by(Feedback.created_at.desc())
        .limit(200)
    )
    return [
        FeedbackRow(
            id=fb.id,
            created_at=fb.created_at,
            kind=fb.kind.value,
            status=fb.status.value,
            reporter=_name(users, fb.user_id),
            routed_to=_name(users, fb.routed_to_user_id),
            question=question,
            comment=fb.comment,
        )
        for fb, question in rows
    ]
