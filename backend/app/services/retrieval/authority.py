"""Authority filter (hard) and authority boost (soft).

Hard filter — a chunk is dropped unless ALL hold (re-derived here in Python, independently of the
SQL pre-filter, so a bug in one layer cannot leak draft or superseded text):
  * its version is approved and is the document's current version as of `as_of`;
  * no confirmed, effective amendment supersedes any clause it covers;
  * the document is network-wide or assigned to the user's branch.

Soft boost — added to the re-ranker score for ordering only (never for the relevance gate):
  * +branch_boost   branch-specific document for the user's branch (local rules beat network-wide);
  * +circular_boost amending circular (it carries the newest instruction for the section it amends);
  * +recency_boost × (1 − age/2y) small preference for recently effective versions.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentVersion
from app.models.enums import VersionStatus
from app.models.supersession import Supersession
from app.services.ingestion.supersession import (
    SupersessionInfo,
    VersionInfo,
    current_versions_by_document,
    is_superseded,
)
from app.services.retrieval.types import Candidate


@dataclass(frozen=True)
class BoostConfig:
    branch: float = 0.10
    circular: float = 0.05
    recency: float = 0.02
    recency_horizon_days: int = 730


@dataclass
class AuthorityContext:
    as_of: date
    branch_id: uuid.UUID | None
    current_version_ids: set[uuid.UUID] = field(default_factory=set)
    links: list[SupersessionInfo] = field(default_factory=list)


def build_context(
    as_of: date,
    branch_id: uuid.UUID | None,
    versions: Iterable[VersionInfo],
    links: Iterable[SupersessionInfo],
) -> AuthorityContext:
    current = current_versions_by_document(versions, as_of)
    return AuthorityContext(
        as_of=as_of,
        branch_id=branch_id,
        current_version_ids={v.id for v in current.values()},
        links=list(links),
    )


async def load_context(session: AsyncSession, as_of: date, branch_id: uuid.UUID | None) -> AuthorityContext:
    version_rows = await session.execute(
        select(
            DocumentVersion.id,
            DocumentVersion.document_id,
            DocumentVersion.status,
            DocumentVersion.effective_from,
            DocumentVersion.approved_at,
        )
    )
    versions = [
        VersionInfo(r.id, r.document_id, VersionStatus(r.status), r.effective_from, r.approved_at) for r in version_rows
    ]
    status_by_id = {v.id: v.status for v in versions}
    link_rows = await session.execute(
        select(
            Supersession.source_version_id,
            Supersession.target_document_id,
            Supersession.target_section_path,
            Supersession.effective_from,
            Supersession.confirmed,
        )
    )
    links = [
        SupersessionInfo(
            source_version_id=r.source_version_id,
            source_status=status_by_id.get(r.source_version_id, VersionStatus.draft),
            target_document_id=r.target_document_id,
            target_section_path=r.target_section_path,
            effective_from=r.effective_from,
            confirmed=r.confirmed,
        )
        for r in link_rows
    ]
    return build_context(as_of, branch_id, versions, links)


def drop_reason(candidate: Candidate, ctx: AuthorityContext) -> str | None:
    if candidate.status != VersionStatus.approved:
        return f"version status is {candidate.status}"
    if candidate.version_id not in ctx.current_version_ids:
        return "not the current version"
    if is_superseded(candidate.document_id, candidate.covered_paths or [candidate.section_path], ctx.links, ctx.as_of):
        return "superseded by an amendment"
    if not candidate.applies_to_all_branches and (ctx.branch_id is None or ctx.branch_id not in candidate.branch_ids):
        return "not applicable to this branch"
    return None


def filter_eligible(candidates: list[Candidate], ctx: AuthorityContext) -> tuple[list[Candidate], int]:
    kept: list[Candidate] = []
    for candidate in candidates:
        reason = drop_reason(candidate, ctx)
        candidate.is_current = candidate.version_id in ctx.current_version_ids
        candidate.is_superseded = reason == "superseded by an amendment"
        if reason is None:
            kept.append(candidate)
    return kept, len(candidates) - len(kept)


def apply_boosts(candidates: list[Candidate], ctx: AuthorityContext, cfg: BoostConfig) -> list[Candidate]:
    for c in candidates:
        boosts: dict[str, float] = {}
        if not c.applies_to_all_branches and ctx.branch_id is not None and ctx.branch_id in c.branch_ids:
            boosts["branch"] = cfg.branch
        if c.doc_type == "circular" and c.supersedes:
            boosts["circular"] = cfg.circular
        age_days = max(0, (ctx.as_of - c.effective_from).days)
        recency = cfg.recency * max(0.0, 1.0 - age_days / cfg.recency_horizon_days)
        if recency > 0:
            boosts["recency"] = round(recency, 4)
        c.boosts = boosts
        c.final_score = round(c.rerank_score + sum(boosts.values()), 6)
    return sorted(candidates, key=lambda c: (-c.final_score, -c.rerank_score))
