"""End-to-end retrieval: normalise → keyword + vector → RRF → authority filter → re-rank → boost."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings.base import EmbeddingProvider
from app.services.retrieval import authority
from app.services.retrieval.abbreviations import expand_query
from app.services.retrieval.hybrid import reciprocal_rank_fusion
from app.services.retrieval.keyword import keyword_search
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.terms import TermStats
from app.services.retrieval.types import Candidate, RetrievalResult
from app.services.retrieval.vector import vector_search
from app.services.textutil import stemmed_words


@dataclass(frozen=True)
class SearchConfig:
    top_k: int = 40
    rrf_k: int = 60
    rerank_candidates: int = 24
    rerank_top_n: int = 12
    k_context: int = 6
    key_term_extra: int = 3
    key_term_boost: float = 0.25
    boosts: authority.BoostConfig = field(default_factory=authority.BoostConfig)


_CANDIDATE_SQL = text(
    """
SELECT c.id AS chunk_id, c.version_id, v.document_id, d.doc_code, d.title, d.doc_type, d.department_id,
       v.version_label, v.status, v.effective_from, v.approved_at, c.section_path, c.covered_paths,
       c.heading, c.text, c.page_start, c.page_end, c.is_table, d.applies_to_all_branches,
       ARRAY(SELECT db.branch_id FROM document_branches db WHERE db.document_id = d.id) AS branch_ids
FROM chunks c
JOIN document_versions v ON v.id = c.version_id
JOIN documents d ON d.id = v.document_id
WHERE c.id = ANY(:ids)
"""
)

_AMENDS_SQL = text(
    """
SELECT s.source_version_id, d.doc_code, s.target_document_id, s.target_section_path
FROM supersessions s JOIN documents d ON d.id = s.target_document_id
WHERE s.confirmed AND s.source_version_id = ANY(:version_ids) AND s.effective_from <= :as_of
ORDER BY d.doc_code, s.target_section_path NULLS FIRST
"""
)


async def load_candidates(session: AsyncSession, chunk_ids: list[uuid.UUID], as_of: date) -> dict[uuid.UUID, Candidate]:
    if not chunk_ids:
        return {}
    rows = (await session.execute(_CANDIDATE_SQL, {"ids": chunk_ids})).mappings().all()
    candidates = {
        row["chunk_id"]: Candidate(
            chunk_id=row["chunk_id"],
            version_id=row["version_id"],
            document_id=row["document_id"],
            doc_code=row["doc_code"],
            title=row["title"],
            doc_type=str(row["doc_type"]),
            department_id=row["department_id"],
            version_label=row["version_label"],
            status=str(row["status"]),
            effective_from=row["effective_from"],
            approved_at=row["approved_at"],
            section_path=row["section_path"],
            covered_paths=list(row["covered_paths"] or []),
            heading=row["heading"],
            text=row["text"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            is_table=row["is_table"],
            applies_to_all_branches=row["applies_to_all_branches"],
            branch_ids=list(row["branch_ids"] or []),
        )
        for row in rows
    }
    version_ids = list({c.version_id for c in candidates.values()})
    amends: dict[uuid.UUID, list[dict[str, object]]] = {}
    for row in (await session.execute(_AMENDS_SQL, {"version_ids": version_ids, "as_of": as_of})).mappings():
        amends.setdefault(row["source_version_id"], []).append(
            {
                "doc_code": row["doc_code"],
                "document_id": str(row["target_document_id"]),
                "section_path": row["target_section_path"],
            }
        )
    for candidate in candidates.values():
        candidate.supersedes = amends.get(candidate.version_id, [])
    return candidates


_ITEM_START = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)]|\([a-z]{1,2}\)|\([ivx]{1,5}\))\s+")


def passage_windows(candidate: Candidate, max_words: int = 60) -> list[str]:
    """Split a passage into short, self-contained windows (MaxP re-ranking).

    A cross-encoder dilutes its score when one chunk covers several topics, so each chunk is
    scored by its best window: a table row (as "Header: value; …"), a list item, or a group of
    sentences. Context goes AFTER the text — "(document title; clause heading)" — which scored
    best for relevant windows on bge-reranker-base without lifting irrelevant ones."""
    suffix = f"\n({candidate.title}; {candidate.heading})"
    windows: list[str] = []
    header: list[str] | None = None
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            windows.append(" ".join(buffer) + suffix)
            buffer.clear()

    for raw in candidate.text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("|"):
            flush()
            if re.fullmatch(r"\|?[\s:|-]+\|?", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if header is None:
                header = cells
                continue
            pairs = "; ".join(f"{h}: {v}" for h, v in zip(header, cells, strict=False) if v)
            windows.append(pairs + suffix)
            continue
        header = None
        if _ITEM_START.match(line):
            flush()
        if buffer and sum(len(b.split()) for b in buffer) + len(line.split()) > max_words:
            flush()
        buffer.append(line)
    flush()
    return windows or [candidate.rerank_text]


async def _maxp_scores(
    reranker: Reranker,
    query: str,
    pool: list[Candidate],
    *,
    windows_per_chunk: int = 2,
    chunk_chars: int = 600,
) -> list[tuple[float, str]]:
    """Per candidate: max(best window, whole chunk with its title first), in one batched call.

    The whole-chunk view catches clauses whose subject only appears in the document title
    (a heparin protocol's "Loading bolus: 80 units/kg" never repeats the word heparin). To keep
    CPU latency down, only each chunk's `windows_per_chunk` windows with the most query words
    are scored."""
    query_words = stemmed_words(query)
    spans: list[tuple[int, int]] = []
    texts: list[str] = []
    for cand in pool:
        wins = passage_windows(cand)
        if len(wins) > windows_per_chunk:
            wins = sorted(wins, key=lambda w: -len(query_words & stemmed_words(w)))[:windows_per_chunk]
        start = len(texts)
        texts += wins
        texts.append(f"{cand.title} — {cand.heading}\n{cand.text[:chunk_chars]}")
        spans.append((start, len(texts)))
    scores = await asyncio.to_thread(reranker.score, query, texts)
    out: list[tuple[float, str]] = []
    for start, end in spans:
        best = max(range(start, end), key=lambda i: scores[i])
        window = texts[best] if best < end - 1 else texts[start]
        out.append((scores[best], window))
    return out


async def search(
    session: AsyncSession,
    *,
    question: str,
    embedder: EmbeddingProvider,
    reranker: Reranker,
    as_of: date,
    branch_id: uuid.UUID | None,
    config: SearchConfig,
    term_stats: TermStats | None = None,
) -> RetrievalResult:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    expanded = expand_query(question)

    query_vector = await asyncio.to_thread(embedder.embed_query, expanded.text)
    timings["embed"] = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    kw = await keyword_search(session, expanded.keyword_text, as_of=as_of, branch_id=branch_id, k=config.top_k)
    vec = await vector_search(session, query_vector, as_of=as_of, branch_id=branch_id, k=config.top_k)
    fused = reciprocal_rank_fusion([[i for i, _ in kw], [i for i, _ in vec]], k=config.rrf_k, limit=config.top_k)
    timings["search"] = (time.perf_counter() - t1) * 1000

    t2 = time.perf_counter()
    by_id = await load_candidates(session, [cid for cid, _ in fused], as_of)
    kw_rank = {cid: r for r, (cid, _) in enumerate(kw, start=1)}
    vec_rank = {cid: r for r, (cid, _) in enumerate(vec, start=1)}
    vec_score = dict(vec)
    ordered: list[Candidate] = []
    for cid, score in fused:
        cand = by_id.get(cid)
        if cand is None:
            continue
        cand.rrf_score = round(score, 6)
        cand.keyword_rank = kw_rank.get(cid)
        cand.vector_rank = vec_rank.get(cid)
        cand.vector_score = vec_score.get(cid)
        ordered.append(cand)
    ctx = await authority.load_context(session, as_of, branch_id)
    eligible, dropped = authority.filter_eligible(ordered, ctx)
    timings["authority"] = (time.perf_counter() - t2) * 1000

    t3 = time.perf_counter()
    key_terms = term_stats.key_terms(expanded.text) if term_stats is not None else set()
    uncovered = term_stats.uncovered_entities(question, expanded.expansions) if term_stats is not None else set()
    pool = eligible[: config.rerank_candidates]
    if key_terms:
        # Passages naming the specific thing asked about (e.g. a drug) always get re-ranked.
        extra = [c for c in eligible[config.rerank_candidates :] if key_terms & stemmed_words(c.rerank_text)]
        pool += extra[: config.key_term_extra]
    for cand, (score, window) in zip(pool, await _maxp_scores(reranker, expanded.text, pool), strict=True):
        cand.rerank_score = round(score, 6)
        cand.best_window = window
    reranked = sorted(pool, key=lambda c: -c.rerank_score)[: config.rerank_top_n]
    boosted = authority.apply_boosts(reranked, ctx, config.boosts)
    if key_terms:
        for cand in boosted:
            matched = key_terms & stemmed_words(cand.rerank_text)
            if matched:
                bonus = round(config.key_term_boost * len(matched) / len(key_terms), 4)
                cand.boosts["key_terms"] = bonus
                cand.final_score = round(cand.final_score + bonus, 6)
        boosted.sort(key=lambda c: (-c.final_score, -c.rerank_score))
    timings["rerank"] = (time.perf_counter() - t3) * 1000
    timings["total"] = (time.perf_counter() - t0) * 1000

    return RetrievalResult(
        query=question,
        expanded_query=expanded.text,
        expansions=expanded.expansions,
        candidates=boosted[: config.k_context],
        reranked=boosted,
        dropped_by_authority=dropped,
        timings_ms={k: round(v, 1) for k, v in timings.items()},
        key_terms=sorted(key_terms),
        uncovered_terms=sorted(uncovered),
    )
