"""PostgreSQL full-text search over eligible chunks (websearch_to_tsquery + ts_rank_cd)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.eligibility import ELIGIBLE_CTE

_SQL = text(
    ELIGIBLE_CTE  # noqa: S608  static SQL; values are bound parameters
    + """
SELECT c.id, ts_rank_cd(c.tsv, q, 32) AS score
FROM chunks c, websearch_to_tsquery('english', :q) AS q
WHERE c.id IN (SELECT id FROM eligible) AND c.tsv @@ q
ORDER BY score DESC, c.id
LIMIT :k
"""
)


async def keyword_search(
    session: AsyncSession, query: str, *, as_of: date, branch_id: uuid.UUID | None, k: int
) -> list[tuple[uuid.UUID, float]]:
    if not query.strip():
        return []
    rows = await session.execute(_SQL, {"q": query, "as_of": as_of, "branch_id": branch_id, "k": k})
    return [(row.id, float(row.score)) for row in rows]
