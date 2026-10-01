"""End-to-end query pipeline (spec §7).

`run()` is an async generator of events shared by POST /query (which returns the final answer)
and the SSE stream: route → sources → answer → done. The `answer` event is only produced after
the verifier has run, so unverified text can never reach a client.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.models.enums import AnswerOutcome, QueryRoute
from app.models.query_log import AnswerLog, Citation, QueryLog
from app.models.user import User
from app.schemas.query import (
    CitationOut,
    ConflictOut,
    ConflictSide,
    ContactOut,
    DocRef,
    EscalationOut,
    QueryResponse,
    QuickValue,
    RouteEvent,
    SourceCard,
    VerificationOut,
)
from app.services import audit
from app.services.generation import abstention, classifier, conflicts, generator, verifier
from app.services.generation.generator import ConflictNote, Passage
from app.services.registry import Services
from app.services.retrieval.search import search
from app.services.retrieval.terms import term_stats
from app.services.retrieval.types import Candidate, RetrievalResult

log = get_logger(__name__)

_MARKER_LIST = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)+)\]")


@dataclass
class QueryEvent:
    event: str  # route | sources | answer | done | error
    data: dict[str, Any]


def normalise_markers(text: str) -> str:
    """ "[S1, S2]" -> "[S1][S2]" so every marker is individually verifiable."""
    return _MARKER_LIST.sub(lambda m: "".join(f"[{x.strip()}]" for x in m.group(1).split(",")), text)


def _snippet(text: str, limit: int = 320) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _amends(c: Candidate) -> list[DocRef]:
    return [DocRef(doc_code=a["doc_code"], section_path=a.get("section_path")) for a in c.supersedes]


def _source_card(marker: str, c: Candidate) -> SourceCard:
    return SourceCard(
        marker=marker,
        chunk_id=c.chunk_id,
        version_id=c.version_id,
        doc_code=c.doc_code,
        title=c.title,
        doc_type=c.doc_type,
        version=c.version_label,
        section_path=c.section_path,
        heading=c.heading,
        page=c.page_start,
        effective_from=c.effective_from,
        snippet=_snippet(c.text),
        relevance=round(c.rerank_score, 4),
        amends=_amends(c),
        branch_specific=not c.applies_to_all_branches,
    )


def _conflict_side(c: Candidate, marker: str | None) -> ConflictSide:
    return ConflictSide(
        marker=marker,
        chunk_id=c.chunk_id,
        doc_code=c.doc_code,
        title=c.title,
        version=c.version_label,
        section_path=c.section_path,
        effective_from=c.effective_from,
        snippet=_snippet(c.text, 400),
    )


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _discard(task: asyncio.Task[Any] | None) -> None:
    """Cancel a speculative task (it owns its own DB session, so cancelling is safe)."""
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


class Orchestrator:
    def __init__(self, services: Services) -> None:
        self.s = services
        self.settings = services.settings
        self._timings: dict[str, int] = {}
        self._trace: dict[str, Any] = {}

    async def answer(
        self, session: AsyncSession, question: str, user: User, branch_id: uuid.UUID | None
    ) -> QueryResponse:
        final: QueryResponse | None = None
        async for event in self.run(session, question, user, branch_id):
            if event.event == "answer":
                final = QueryResponse.model_validate(event.data)
        assert final is not None
        return final

    async def run(
        self, session: AsyncSession, question: str, user: User, branch_id: uuid.UUID | None
    ) -> AsyncIterator[QueryEvent]:
        started = time.perf_counter()
        branch = branch_id or user.branch_id
        as_of = self.settings.today()
        query_id = uuid.uuid4()

        # 1. Redact before anything else touches the question.
        redaction = await asyncio.to_thread(self.s.redactor.redact, question)
        redacted = redaction.text

        # 2. Route. Deterministic rules run first; unless they already flag a patient-specific
        #    question, retrieval starts in parallel with the LLM classifier (it is discarded if
        #    the route turns out not to be "answer").
        timings: dict[str, int] = {}
        self._timings = timings
        stage = time.perf_counter()
        retrieval_task: asyncio.Task[RetrievalResult] | None = None
        if classifier.rule_classify(redacted).route != QueryRoute.high_risk:
            retrieval_task = asyncio.create_task(self._retrieve(redacted, as_of, branch))
        try:
            route = await classifier.classify(redacted, self.s.llm, self.s.prompts)
        except BaseException:
            await _discard(retrieval_task)
            raise
        timings["route"] = _ms(stage)
        self._trace = {"route_reason": route.reason, "route_source": route.source}
        yield QueryEvent(
            "route",
            RouteEvent(
                route=route.route,
                reason=route.reason,
                redacted_question=redacted,
                pii_redacted=redaction.changed,
            ).model_dump(mode="json"),
        )

        if route.route != QueryRoute.answer:
            await _discard(retrieval_task)
            reasons: dict[QueryRoute, abstention.AbstainReason] = {
                QueryRoute.high_risk: "high_risk",
                QueryRoute.out_of_scope: "out_of_scope",
                QueryRoute.clarify: "clarify",
            }
            reason = reasons[route.route]
            escalation = await abstention.build(session, reason, branch, clarifying_question=route.clarifying_question)
            response = await self._finish_abstained(
                session,
                query_id,
                user,
                branch,
                redacted,
                redaction.changed,
                route.route,
                escalation,
                started,
                sources=[],
                retrieval_summary=[],
                mode=None,
            )
            yield QueryEvent("answer", response.model_dump(mode="json"))
            yield QueryEvent("done", {"query_id": str(query_id)})
            return

        # 3. Retrieve (authority-filtered, re-ranked) — usually already finished by now.
        stage = time.perf_counter()
        retrieval = await (retrieval_task or self._retrieve(redacted, as_of, branch))
        timings["retrieve"] = int(retrieval.timings_ms.get("total", 0))
        timings["retrieve_wait"] = _ms(stage)
        min_rel = self.settings.min_relevance
        self._trace.update(
            expansions=[f"{term} = {meaning}" for term, meaning in retrieval.expansions],
            key_terms=retrieval.key_terms,
            uncovered_terms=retrieval.uncovered_terms,
            dropped_by_authority=retrieval.dropped_by_authority,
            top_relevance=round(retrieval.top_relevance, 4),
        )

        def useful(c: Candidate) -> bool:
            # Relevant by the re-ranker, or it names the specific thing asked about (key term).
            return c.rerank_score >= min_rel * 0.5 or "key_terms" in c.boosts

        context = [c for c in retrieval.candidates if useful(c)] or retrieval.candidates
        cards = [_source_card(f"S{i}", c) for i, c in enumerate(context, start=1) if useful(c)]
        yield QueryEvent(
            "sources",
            {"sources": [c.model_dump(mode="json") for c in cards], "timings_ms": retrieval.timings_ms},
        )
        retrieval_summary = [
            {
                "chunk_id": str(c.chunk_id),
                "label": c.label,
                "rerank": c.rerank_score,
                "final": c.final_score,
                "boosts": c.boosts,
            }
            for c in retrieval.reranked
        ]
        departments = list({c.department_id for c in context if c.department_id and c.rerank_score >= min_rel})

        if retrieval.uncovered_terms:
            log.info("question_names_uncovered_entity", terms=retrieval.uncovered_terms)
        if not context or retrieval.top_relevance < min_rel or retrieval.uncovered_terms:
            escalation = await abstention.build(session, "not_found", branch, department_ids=departments)
            response = await self._finish_abstained(
                session,
                query_id,
                user,
                branch,
                redacted,
                redaction.changed,
                QueryRoute.answer,
                escalation,
                started,
                sources=cards,
                retrieval_summary=retrieval_summary,
                mode=None,
            )
            yield QueryEvent("answer", response.model_dump(mode="json"))
            yield QueryEvent("done", {"query_id": str(query_id)})
            return

        # 4. Conflicts (may pull the other side of a known conflict into the context).
        found_conflicts, context = await conflicts.detect_at_query_time(
            session, context, as_of=as_of, branch_id=branch, min_relevance=self.settings.min_relevance
        )
        passages = generator.build_passages(context)
        marker_of = {p.candidate.chunk_id: p.marker for p in passages}
        notes = [
            ConflictNote(marker_of[c.a.chunk_id], marker_of[c.b.chunk_id], c.description)
            for c in found_conflicts
            if c.a.chunk_id in marker_of and c.b.chunk_id in marker_of
        ]

        # 5. Generate, then verify every claim.
        stage = time.perf_counter()
        draft = await generator.generate(
            redacted,
            passages,
            notes,
            self.s.llm,
            self.s.prompts,
            key_terms=set(retrieval.key_terms),
            glossary=retrieval.expansions,
            unit_scorer=self.s.reranker.score,
        )
        timings["generate"] = _ms(stage)
        if draft.llm_error:
            log.warning("generation_fell_back_to_extractive", reason=draft.llm_error)
        draft.answer = normalise_markers(draft.answer)
        if draft.not_found:
            escalation = await abstention.build(session, "not_found", branch, department_ids=departments)
            response = await self._finish_abstained(
                session,
                query_id,
                user,
                branch,
                redacted,
                redaction.changed,
                QueryRoute.answer,
                escalation,
                started,
                sources=cards,
                retrieval_summary=retrieval_summary,
                mode=draft.mode,
            )
            yield QueryEvent("answer", response.model_dump(mode="json"))
            yield QueryEvent("done", {"query_id": str(query_id)})
            return

        stage = time.perf_counter()
        checked = await verifier.verify(
            draft,
            passages,
            llm=self.s.llm if draft.mode == "llm" else None,
            prompts=self.s.prompts,
            threshold=self.settings.verifier_threshold,
            nli=self.s.nli,
            mode=self.settings.verifier_mode,
            glossary=retrieval.expansions,
        )
        timings["verify"] = _ms(stage)
        if not checked.has_supported_claims:
            escalation = await abstention.build(session, "not_found", branch, department_ids=departments)
            response = await self._finish_abstained(
                session,
                query_id,
                user,
                branch,
                redacted,
                redaction.changed,
                QueryRoute.answer,
                escalation,
                started,
                sources=cards,
                retrieval_summary=retrieval_summary,
                mode=draft.mode,
                verifier_summary=checked.summary,
            )
            yield QueryEvent("answer", response.model_dump(mode="json"))
            yield QueryEvent("done", {"query_id": str(query_id)})
            return

        outcome = AnswerOutcome.answered if checked.supported_ratio == 1.0 else AnswerOutcome.partial
        response = await self._finish_answered(
            session,
            query_id,
            user,
            branch,
            redacted,
            redaction.changed,
            passages,
            checked,
            found_conflicts,
            outcome,
            draft.mode,
            started,
            cards,
            retrieval_summary,
        )
        yield QueryEvent("answer", response.model_dump(mode="json"))
        yield QueryEvent("done", {"query_id": str(query_id)})

    # ----------------------------------------------------------------------------------------------

    async def _retrieve(self, question: str, as_of: Any, branch: uuid.UUID | None) -> RetrievalResult:
        # Own session: retrieval may run concurrently with routing and be cancelled.
        async with get_sessionmaker()() as session:
            return await search(
                session,
                question=question,
                embedder=self.s.embedder,
                reranker=self.s.reranker,
                as_of=as_of,
                branch_id=branch,
                config=self.s.search_config,
                term_stats=term_stats,
            )

    def _latency(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    async def _finish_abstained(
        self,
        session: AsyncSession,
        query_id: uuid.UUID,
        user: User,
        branch: uuid.UUID | None,
        redacted: str,
        pii: bool,
        route: QueryRoute,
        escalation: abstention.Escalation,
        started: float,
        *,
        sources: list[SourceCard],
        retrieval_summary: list[dict[str, Any]],
        mode: str | None,
        verifier_summary: dict[str, Any] | None = None,
    ) -> QueryResponse:
        latency = self._latency(started)
        response = QueryResponse(
            query_id=query_id,
            route=route,
            outcome=AnswerOutcome.abstained,
            answer=None,
            escalation=EscalationOut(
                reason=escalation.reason,
                message=escalation.message,
                contacts=[ContactOut.model_validate(c) for c in escalation.contacts],
                clarifying_question=escalation.clarifying_question,
            ),
            sources=sources if escalation.reason == "not_found" else [],
            generation_mode=mode,
            redacted_question=redacted,
            pii_redacted=pii,
            latency_ms=latency,
        )
        await self._persist(
            session,
            response,
            user,
            branch,
            retrieval_summary,
            verifier_summary,
            abstain_reason=escalation.reason,
            passages=[],
        )
        return response

    async def _finish_answered(
        self,
        session: AsyncSession,
        query_id: uuid.UUID,
        user: User,
        branch: uuid.UUID | None,
        redacted: str,
        pii: bool,
        passages: list[Passage],
        checked: verifier.Verification,
        found_conflicts: list[conflicts.QueryConflict],
        outcome: AnswerOutcome,
        mode: str,
        started: float,
        cards: list[SourceCard],
        retrieval_summary: list[dict[str, Any]],
    ) -> QueryResponse:
        by_marker = {p.marker: p for p in passages}
        support: dict[str, float] = {}
        for claim in checked.claims:
            if claim.supported and claim.supported_by:
                support[claim.supported_by] = max(support.get(claim.supported_by, 0.0), claim.score)
        citations: list[CitationOut] = []
        for marker in checked.used_markers:
            c = by_marker[marker].candidate
            amends = _amends(c)
            citations.append(
                CitationOut(
                    marker=marker,
                    chunk_id=c.chunk_id,
                    version_id=c.version_id,
                    document_id=c.document_id,
                    doc_code=c.doc_code,
                    title=c.title,
                    doc_type=c.doc_type,
                    version=c.version_label,
                    section_path=c.section_path,
                    heading=c.heading,
                    page=c.page_start,
                    effective_from=c.effective_from,
                    supersedes=amends[0] if amends else None,
                    amends=amends,
                    snippet=_snippet(c.text),
                    supported=True,
                    support_score=round(support[marker], 3) if marker in support else None,
                    branch_specific=not c.applies_to_all_branches,
                )
            )
        used_chunks = {by_marker[m].candidate.chunk_id for m in checked.used_markers}
        marker_of = {p.candidate.chunk_id: p.marker for p in passages}
        conflict_out = [
            ConflictOut(
                id=qc.conflict_id,
                description=qc.description,
                a=_conflict_side(qc.a, marker_of.get(qc.a.chunk_id)),
                b=_conflict_side(qc.b, marker_of.get(qc.b.chunk_id)),
                newer="a"
                if qc.a.effective_from > qc.b.effective_from
                else ("b" if qc.b.effective_from > qc.a.effective_from else None),
                status=qc.status,
                detected_by=qc.detected_by,
                flagged_to_owner=qc.conflict_id is not None,
            )
            for qc in found_conflicts
            if qc.a.chunk_id in used_chunks or qc.b.chunk_id in used_chunks
        ]
        response = QueryResponse(
            query_id=query_id,
            route=QueryRoute.answer,
            outcome=outcome,
            answer=checked.answer,
            citations=citations,
            quick_values=[QuickValue.model_validate(q) for q in checked.quick_values],
            conflicts=conflict_out,
            sources=cards,
            generation_mode=mode,
            verification=VerificationOut(
                claims=checked.summary["claims"], supported=checked.summary["supported"], judge=checked.judge
            ),
            redacted_question=redacted,
            pii_redacted=pii,
            latency_ms=self._latency(started),
        )
        await self._persist(
            session,
            response,
            user,
            branch,
            retrieval_summary,
            checked.summary,
            abstain_reason=None,
            passages=passages,
            claims=checked.claims,
        )
        return response

    async def _persist(
        self,
        session: AsyncSession,
        response: QueryResponse,
        user: User,
        branch: uuid.UUID | None,
        retrieval_summary: list[dict[str, Any]],
        verifier_summary: dict[str, Any] | None,
        *,
        abstain_reason: str | None,
        passages: list[Passage],
        claims: list[verifier.ClaimCheck] | None = None,
    ) -> None:
        response.timings_ms = {**self._timings, "total": response.latency_ms}
        query_log = QueryLog(
            id=response.query_id,
            user_id=user.id,
            branch_id=branch,
            redacted_question=response.redacted_question,
            pii_redacted=response.pii_redacted,
            route=response.route,
            latency_ms=response.latency_ms,
            model_id=self.s.model_id,
            prompt_version=self.s.prompts.version,
            retrieval=retrieval_summary,
            trace={**self._trace, "timings_ms": response.timings_ms},
        )
        session.add(query_log)
        answer_log = AnswerLog(
            query_id=response.query_id,
            answer_text=response.answer,
            outcome=response.outcome,
            abstain_reason=abstain_reason,
            generation_mode=response.generation_mode,
            verifier_summary=verifier_summary,
            conflicts=[c.model_dump(mode="json") for c in response.conflicts],
            quick_values=[q.model_dump() for q in response.quick_values],
        )
        session.add(answer_log)
        await session.flush()
        by_marker = {p.marker: p for p in passages}
        for citation in response.citations:
            claim_text = next((c.text for c in (claims or []) if c.supported and citation.marker in c.markers), None)
            session.add(
                Citation(
                    answer_id=answer_log.id,
                    marker=citation.marker,
                    chunk_id=citation.chunk_id,
                    version_id=by_marker[citation.marker].candidate.version_id,
                    claim_text=claim_text,
                    supported=citation.supported,
                    support_score=citation.support_score,
                )
            )
        await audit.record(
            session,
            action="query.answered" if response.outcome != AnswerOutcome.abstained else "query.abstained",
            entity_type="query",
            entity_id=response.query_id,
            actor_user_id=user.id,
            payload={
                "route": response.route.value,
                "outcome": response.outcome.value,
                "reason": abstain_reason,
                "cited_chunks": [str(c.chunk_id) for c in response.citations],
                "prompt_version": self.s.prompts.version,
                "model_id": self.s.model_id,
                "latency_ms": response.latency_ms,
            },
        )
        await session.commit()
        log.info(
            "query_completed",
            query_id=str(response.query_id),
            route=response.route.value,
            outcome=response.outcome.value,
            reason=abstain_reason,
            citations=len(response.citations),
            latency_ms=response.latency_ms,
            pii_redacted=response.pii_redacted,
        )
