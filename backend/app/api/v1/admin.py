from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import case, func, select, text

from app.api.deps import AdminUser, AuthorUser, DbSession, ServicesDep
from app.core.errors import NotFoundError
from app.models.audit import AuditEvent
from app.models.branch import Branch
from app.models.chunk import Chunk
from app.models.conflict import Conflict
from app.models.department import Department
from app.models.document import Document, DocumentVersion
from app.models.enums import ConflictStatus, DocType, IngestStatus, VersionStatus
from app.models.feedback import Feedback
from app.models.supersession import Supersession
from app.models.user import User
from app.schemas.admin import (
    AuditEventOut,
    AuditVerifyOut,
    ConflictAdminOut,
    ConflictPatch,
    ConflictSideOut,
    CountItem,
    DailyPoint,
    ReferenceData,
    StaleDoc,
    StatsOut,
)
from app.schemas.document import BranchOut, DepartmentOut, UserOut
from app.services import audit

router = APIRouter(tags=["admin"])


@router.get("/admin/stats", response_model=StatsOut)
async def stats(user: AdminUser, session: DbSession, services: ServicesDep, days: int = 30) -> StatsOut:
    days = max(1, min(days, 365))
    since = datetime.now(UTC) - timedelta(days=days)
    today = services.settings.today()
    params = {"since": since}

    totals = (
        (
            await session.execute(
                text("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE a.outcome = 'answered') AS answered,
               count(*) FILTER (WHERE a.outcome = 'partial') AS partial,
               count(*) FILTER (WHERE a.outcome = 'abstained') AS abstained,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY q.latency_ms) AS p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY q.latency_ms) AS p95
        FROM query_logs q LEFT JOIN answer_logs a ON a.query_id = q.id
        WHERE q.created_at >= :since"""),
                params,
            )
        )
        .mappings()
        .one()
    )
    routes: dict[str, int] = dict(
        (
            await session.execute(
                text("SELECT route, count(*) FROM query_logs WHERE created_at >= :since GROUP BY route"),
                params,
            )
        ).all()
    )
    reasons: dict[str, int] = dict(
        (
            await session.execute(
                text("""
        SELECT a.abstain_reason, count(*) FROM answer_logs a JOIN query_logs q ON q.id = a.query_id
        WHERE q.created_at >= :since AND a.abstain_reason IS NOT NULL GROUP BY a.abstain_reason"""),
                params,
            )
        ).all()
    )
    top_q = (
        await session.execute(
            text("""
        SELECT lower(redacted_question) AS label, count(*) AS n FROM query_logs WHERE created_at >= :since
        GROUP BY lower(redacted_question) ORDER BY n DESC, label LIMIT 10"""),
            params,
        )
    ).all()
    unanswered = (
        await session.execute(
            text("""
        SELECT lower(q.redacted_question) AS label, count(*) AS n
        FROM query_logs q JOIN answer_logs a ON a.query_id = q.id
        WHERE q.created_at >= :since AND a.abstain_reason = 'not_found'
        GROUP BY lower(q.redacted_question) ORDER BY n DESC, label LIMIT 10"""),
            params,
        )
    ).all()
    top_docs = (
        await session.execute(
            text("""
        SELECT d.doc_code AS label, count(*) AS n FROM citations c
        JOIN document_versions v ON v.id = c.version_id JOIN documents d ON d.id = v.document_id
        JOIN answer_logs a ON a.id = c.answer_id JOIN query_logs q ON q.id = a.query_id
        WHERE q.created_at >= :since GROUP BY d.doc_code ORDER BY n DESC LIMIT 10"""),
            params,
        )
    ).all()
    daily = (
        await session.execute(
            text("""
        SELECT date_trunc('day', q.created_at)::date AS day, count(*) AS n,
               count(*) FILTER (WHERE a.outcome = 'abstained') AS abstained
        FROM query_logs q LEFT JOIN answer_logs a ON a.query_id = q.id
        WHERE q.created_at >= :since GROUP BY 1 ORDER BY 1"""),
            params,
        )
    ).all()

    stale_rows = (
        await session.execute(
            select(DocumentVersion, Document)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.status == VersionStatus.approved, DocumentVersion.review_due < today)
            .order_by(DocumentVersion.review_due)
        )
    ).all()
    open_conflicts = (
        await session.execute(select(func.count()).select_from(Conflict).where(Conflict.status == ConflictStatus.open))
    ).scalar_one()
    open_feedback = (
        await session.execute(
            select(func.count()).select_from(Feedback).where(Feedback.status != "resolved", Feedback.kind != "helpful")
        )
    ).scalar_one()
    pending_links = (
        await session.execute(select(func.count()).select_from(Supersession).where(Supersession.confirmed.is_(False)))
    ).scalar_one()
    awaiting = (
        await session.execute(
            select(func.count())
            .select_from(DocumentVersion)
            .where(
                DocumentVersion.status == VersionStatus.draft,
                DocumentVersion.ingest_status == IngestStatus.ready,
            )
        )
    ).scalar_one()

    total = int(totals["total"] or 0)
    abstained = int(totals["abstained"] or 0)
    return StatsOut(
        window_days=days,
        total_questions=total,
        answered=int(totals["answered"] or 0),
        partial=int(totals["partial"] or 0),
        abstained=abstained,
        abstention_rate=round(abstained / total, 4) if total else 0.0,
        route_counts={str(k): int(v) for k, v in routes.items()},
        abstain_reasons={str(k): int(v) for k, v in reasons.items()},
        latency_p50_ms=float(totals["p50"]) if totals["p50"] is not None else None,
        latency_p95_ms=float(totals["p95"]) if totals["p95"] is not None else None,
        top_questions=[CountItem(label=r[0], count=r[1]) for r in top_q],
        unanswered_questions=[CountItem(label=r[0], count=r[1]) for r in unanswered],
        top_documents=[CountItem(label=r[0], count=r[1]) for r in top_docs],
        stale_documents=[
            StaleDoc(
                document_id=d.id,
                doc_code=d.doc_code,
                title=d.title,
                version=v.version_label,
                review_due=v.review_due,
                days_overdue=(today - v.review_due).days,
            )
            for v, d in stale_rows
            if v.review_due
        ],
        open_conflicts=open_conflicts,
        open_feedback=open_feedback,
        pending_supersessions=pending_links,
        documents_awaiting_approval=awaiting,
        daily=[DailyPoint(day=r[0], questions=r[1], abstained=r[2]) for r in daily],
    )


# --- conflicts -------------------------------------------------------------------------------------


async def _side(session: DbSession, chunk: Chunk) -> ConflictSideOut:
    version = await session.get(DocumentVersion, chunk.version_id)
    assert version is not None
    doc = await session.get(Document, version.document_id)
    assert doc is not None
    return ConflictSideOut(
        chunk_id=chunk.id,
        doc_code=doc.doc_code,
        title=doc.title,
        version=version.version_label,
        section_path=chunk.section_path,
        text=chunk.text,
        effective_from=version.effective_from,
    )


@router.get("/conflicts", response_model=list[ConflictAdminOut])
async def list_conflicts(
    user: AuthorUser, session: DbSession, status: ConflictStatus | None = None
) -> list[ConflictAdminOut]:
    stmt = select(Conflict).order_by(
        case((Conflict.status == ConflictStatus.open, 0), else_=1), Conflict.created_at.desc()
    )
    if status:
        stmt = stmt.where(Conflict.status == status)
    out = []
    for c in (await session.execute(stmt)).scalars():
        owner = await session.get(User, c.owner_user_id) if c.owner_user_id else None
        out.append(
            ConflictAdminOut(
                id=c.id,
                description=c.description,
                detected_by=str(c.detected_by),
                status=c.status,
                confidence=c.confidence,
                created_at=c.created_at,
                owner=owner.display_name if owner else None,
                resolution_note=c.resolution_note,
                a=await _side(session, c.chunk_a),
                b=await _side(session, c.chunk_b),
            )
        )
    return out


@router.patch("/conflicts/{conflict_id}", response_model=ConflictAdminOut)
async def update_conflict(
    conflict_id: uuid.UUID, body: ConflictPatch, user: AuthorUser, session: DbSession
) -> ConflictAdminOut:
    conflict = await session.get(Conflict, conflict_id)
    if conflict is None:
        raise NotFoundError("Conflict not found")
    conflict.status = body.status
    conflict.resolution_note = body.resolution_note
    if body.status != ConflictStatus.open:
        conflict.resolved_by, conflict.resolved_at = user.id, datetime.now(UTC)
    await audit.record(
        session,
        action="conflict.updated",
        entity_type="conflict",
        entity_id=conflict.id,
        actor_user_id=user.id,
        payload={"status": body.status.value},
    )
    await session.commit()
    owner = await session.get(User, conflict.owner_user_id) if conflict.owner_user_id else None
    return ConflictAdminOut(
        id=conflict.id,
        description=conflict.description,
        detected_by=str(conflict.detected_by),
        status=conflict.status,
        confidence=conflict.confidence,
        created_at=conflict.created_at,
        owner=owner.display_name if owner else None,
        resolution_note=conflict.resolution_note,
        a=await _side(session, conflict.chunk_a),
        b=await _side(session, conflict.chunk_b),
    )


# --- audit -----------------------------------------------------------------------------------------


@router.get("/admin/audit", response_model=list[AuditEventOut])
async def audit_export(
    user: AdminUser,
    session: DbSession,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    action: str | None = None,
    format: Literal["json", "csv"] = "json",
    limit: int = 500,
) -> Response | list[AuditEventOut]:
    stmt = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(max(1, min(limit, 10000)))
    if from_:
        stmt = stmt.where(AuditEvent.created_at >= datetime.combine(from_, datetime.min.time(), UTC))
    if to:
        stmt = stmt.where(AuditEvent.created_at < datetime.combine(to + timedelta(days=1), datetime.min.time(), UTC))
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    events = list((await session.execute(stmt)).scalars())
    actors = {u.id: u.display_name for u in (await session.execute(select(User))).scalars()}
    rows = [
        AuditEventOut(
            seq=e.seq,
            created_at=e.created_at,
            actor=actors.get(e.actor_user_id) if e.actor_user_id else None,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            payload=e.payload,
            hash=e.hash,
            prev_hash=e.prev_hash,
        )
        for e in events
    ]
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "seq",
                "created_at",
                "actor",
                "action",
                "entity_type",
                "entity_id",
                "payload",
                "prev_hash",
                "hash",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.seq,
                    r.created_at.isoformat(),
                    r.actor or "",
                    r.action,
                    r.entity_type,
                    r.entity_id or "",
                    audit.canonical_json(r.payload),
                    r.prev_hash,
                    r.hash,
                ]
            )
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="protocite-audit.csv"'},
        )
    return rows


@router.get("/admin/audit/verify", response_model=AuditVerifyOut)
async def audit_verify(user: AdminUser, session: DbSession) -> AuditVerifyOut:
    result = await audit.verify_chain(session)
    return AuditVerifyOut(
        ok=result.ok,
        events_checked=result.events_checked,
        first_bad_seq=result.first_bad_seq,
        reason=result.reason,
    )


@router.get("/admin/reference-data", response_model=ReferenceData)
async def reference_data(user: AuthorUser, session: DbSession) -> ReferenceData:
    branches = (await session.execute(select(Branch).order_by(Branch.name))).scalars().all()
    departments = (await session.execute(select(Department).order_by(Department.name))).scalars().all()
    users = (
        (await session.execute(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))
        .scalars()
        .all()
    )
    return ReferenceData(
        branches=[BranchOut.model_validate(b) for b in branches],
        departments=[DepartmentOut.model_validate(d) for d in departments],
        users=[UserOut.model_validate(u) for u in users],
        doc_types=[t.value for t in DocType],
    )
