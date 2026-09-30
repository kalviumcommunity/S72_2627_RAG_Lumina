"""pgvector cosine similarity over eligible chunks."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.eligibility import ELIGIBLE_CTE

_SQL = text(
    ELIGIBLE_CTE  # noqa: S608  static SQL; values are bound parameters
    + """
SELECT c.id, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
FROM chunks c
WHERE c.id IN (SELECT id FROM eligible) AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> CAST(:qvec AS vector), c.id
LIMIT :k
"""
)


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


async def vector_search(
    session: AsyncSession, query_vector: list[float], *, as_of: date, branch_id: uuid.UUID | None, k: int
) -> list[tuple[uuid.UUID, float]]:
    rows = await session.execute(
        _SQL, {"qvec": vector_literal(query_vector), "as_of": as_of, "branch_id": branch_id, "k": k}
    )
    return [(row.id, float(row.score)) for row in rows]
