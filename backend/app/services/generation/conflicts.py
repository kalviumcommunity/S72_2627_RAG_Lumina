"""Query-time conflict surfacing.

1. Open `conflicts` rows that involve a retrieved chunk are surfaced; if the other side of the
   conflict was not retrieved but is still eligible, it is pulled into the context so the answer
   can show both values.
2. The heuristic detector runs on pairs of relevant context chunks from different documents; a new
   finding is stored (detected_by="query") and routed to the document owner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.conflict import Conflict
from app.models.document import Document, DocumentVersion
from app.models.enums import ConflictStatus, DetectedBy
from app.services import audit
from app.services.ingestion.conflict import heuristic_conflict
from app.services.retrieval import authority
from app.services.retrieval.search import load_candidates
from app.services.retrieval.types import Candidate


@dataclass
class QueryConflict:
    a: Candidate
    b: Candidate
    description: str
    conflict_id: uuid.UUID | None
    detected_by: str
    status: str = "open"
    owner_user_id: uuid.UUID | None = None


def _pair_key(x: uuid.UUID, y: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (x, y) if str(x) < str(y) else (y, x)


async def _owner_of(session: AsyncSession, chunk_id: uuid.UUID) -> uuid.UUID | None:
    row = await session.execute(
        select(Document.owner_user_id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(Chunk, Chunk.version_id == DocumentVersion.id)
        .where(Chunk.id == chunk_id)
    )
    return row.scalar_one_or_none()


async def detect_at_query_time(
    session: AsyncSession,
    context: list[Candidate],
    *,
    as_of: date,
    branch_id: uuid.UUID | None,
    min_relevance: float,
    persist: bool = True,
) -> tuple[list[QueryConflict], list[Candidate]]:
    """Return (conflicts, context) — context may gain the other side of a stored conflict."""
    relevant = [c for c in context if c.rerank_score >= min_relevance]
    if not relevant:
        return [], context
    by_id = {c.chunk_id: c for c in context}
    found: dict[tuple[uuid.UUID, uuid.UUID], QueryConflict] = {}

    ids = [c.chunk_id for c in relevant]
    stored = (
        (
            await session.execute(
                select(Conflict).where(
                    Conflict.status == ConflictStatus.open,
                    or_(Conflict.chunk_a_id.in_(ids), Conflict.chunk_b_id.in_(ids)),
                )
            )
        )
        .scalars()
        .all()
    )
    missing = {cid for row in stored for cid in (row.chunk_a_id, row.chunk_b_id) if cid not in by_id}
    if missing:
        extra = await load_candidates(session, list(missing), as_of)
        ctx = await authority.load_context(session, as_of, branch_id)
        eligible, _ = authority.filter_eligible(list(extra.values()), ctx)
        for cand in eligible:
            anchor = next((r for r in stored if cand.chunk_id in (r.chunk_a_id, r.chunk_b_id)), None)
            partner = None
            if anchor is not None:
                other = anchor.chunk_b_id if anchor.chunk_a_id == cand.chunk_id else anchor.chunk_a_id
                partner = by_id.get(other)
            cand.rerank_score = partner.rerank_score if partner else 0.0
            cand.final_score = cand.rerank_score
            by_id[cand.chunk_id] = cand
            context = [*context, cand]
    for row in stored:
        a, b = by_id.get(row.chunk_a_id), by_id.get(row.chunk_b_id)
        if a and b:
            found[_pair_key(a.chunk_id, b.chunk_id)] = QueryConflict(
                a, b, row.description, row.id, str(row.detected_by), str(row.status), row.owner_user_id
            )

    for i, a in enumerate(relevant):
        for b in relevant[i + 1 :]:
            if a.document_id == b.document_id or _pair_key(a.chunk_id, b.chunk_id) in found:
                continue
            if a.applies_to_all_branches != b.applies_to_all_branches:
                continue  # a branch-specific document deliberately overrides the network-wide one
            finding = heuristic_conflict(a.text, b.text)
            if not finding.contradicts:
                continue
            first, second = (a, b) if a.effective_from <= b.effective_from else (b, a)
            conflict_id: uuid.UUID | None = None
            owner = await _owner_of(session, first.chunk_id)
            if persist:
                key = _pair_key(first.chunk_id, second.chunk_id)
                existing = (
                    await session.execute(
                        select(Conflict).where(Conflict.chunk_a_id == key[0], Conflict.chunk_b_id == key[1])
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.status != ConflictStatus.open:
                        continue  # a reviewer already resolved or dismissed this pair
                    conflict_id = existing.id
                else:
                    row = Conflict(
                        chunk_a_id=key[0],
                        chunk_b_id=key[1],
                        detected_by=DetectedBy.query,
                        description=finding.description,
                        confidence=finding.confidence,
                        owner_user_id=owner,
                    )
                    session.add(row)
                    await session.flush()
                    conflict_id = row.id
                    await audit.record(
                        session,
                        action="conflict.detected",
                        entity_type="conflict",
                        entity_id=row.id,
                        payload={
                            "detected_by": "query",
                            "chunks": [str(key[0]), str(key[1])],
                            "routed_to": str(owner) if owner else None,
                        },
                    )
            found[_pair_key(a.chunk_id, b.chunk_id)] = QueryConflict(
                first, second, finding.description, conflict_id, "query", "open", owner
            )
    return list(found.values()), context
