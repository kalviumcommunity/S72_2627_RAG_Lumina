"""Background tasks (arq signature: first argument is the job context)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.models.document import Document, DocumentVersion
from app.models.enums import VersionStatus
from app.services import audit
from app.services.ingestion.pipeline import after_approval, ingest_version, refresh_version_statuses
from app.services.registry import get_services

log = get_logger(__name__)


async def ingest_document(ctx: dict[str, Any], version_id: str, actor_user_id: str | None = None) -> dict[str, Any]:
    async with get_sessionmaker()() as session:
        report = await ingest_version(
            session,
            get_services(),
            uuid.UUID(version_id),
            actor_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        )
    return {"status": report.status, "chunks": report.chunks, "error": report.error}


async def post_approval(ctx: dict[str, Any], version_id: str) -> dict[str, Any]:
    async with get_sessionmaker()() as session:
        return await after_approval(session, get_services(), uuid.UUID(version_id))


async def review_date_reminders(ctx: dict[str, Any]) -> dict[str, Any]:
    """Daily: record overdue / due-soon reviews in the audit log and refresh superseded statuses."""
    services = get_services()
    today = services.settings.today()
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(DocumentVersion, Document.doc_code, Document.owner_user_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.status == VersionStatus.approved,
                    DocumentVersion.review_due.is_not(None),
                    DocumentVersion.review_due <= today + timedelta(days=30),
                )
            )
        ).all()
        for version, doc_code, owner in rows:
            await audit.record(
                session,
                action="review.reminder",
                entity_type="document_version",
                entity_id=version.id,
                payload={
                    "doc_code": doc_code,
                    "review_due": version.review_due.isoformat() if version.review_due else None,
                    "overdue": bool(version.review_due and version.review_due < today),
                    "owner_user_id": str(owner) if owner else None,
                },
            )
        doc_ids = [d for (d,) in await session.execute(select(Document.id))]
        superseded = []
        for doc_id in doc_ids:
            superseded += await refresh_version_statuses(session, doc_id, today)
        await session.commit()
    log.info("review_reminders_sent", count=len(rows), superseded=len(superseded))
    return {"reminders": len(rows), "superseded": len(superseded)}
