"""Ingestion of the synthetic corpus through the real pipeline (parse → OCR → chunk → embed → index)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text

from app.db.session import get_sessionmaker
from app.models import Branch, Chunk, Document, DocumentVersion, Supersession
from app.models.enums import IngestStatus, VersionStatus
from app.services.ingestion import ocr
from app.services.registry import Services
from app.services.retrieval import authority
from app.services.retrieval.eligibility import ELIGIBLE_CTE
from app.services.retrieval.search import load_candidates
from tests.integration.conftest import scalar


async def _version(doc_code: str, label: str) -> DocumentVersion:
    async with get_sessionmaker()() as session:
        return (
            await session.execute(
                select(DocumentVersion)
                .join(Document)
                .where(Document.doc_code == doc_code, DocumentVersion.version_label == label)
            )
        ).scalar_one()


async def _paths(doc_code: str, label: str) -> list[str]:
    version = await _version(doc_code, label)
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Chunk.section_path).where(Chunk.version_id == version.id).order_by(Chunk.ordinal)
        )
        return list(rows.scalars())


async def test_every_version_is_ingested(corpus: dict[str, Any]) -> None:
    assert corpus["versions_created"] == 11
    assert await scalar("SELECT count(*) FROM document_versions WHERE ingest_status <> 'ready'") == 0
    assert await scalar("SELECT count(*) FROM chunks WHERE embedding IS NULL") == 0


async def test_clause_level_section_paths(corpus: dict[str, Any]) -> None:
    paths = await _paths("P-ICU-07", "3")
    for expected in ("1", "2", "4.1", "4.2", "4.3", "5", "6", "7"):
        assert expected in paths
    version = await _version("P-ICU-07", "3")
    async with get_sessionmaker()() as session:
        nomogram = (
            await session.execute(select(Chunk).where(Chunk.version_id == version.id, Chunk.section_path == "4.2"))
        ).scalar_one()
    assert nomogram.is_table and "| Above 100 |" in nomogram.text
    assert nomogram.context_header.startswith("[P-ICU-07 v3 §4.2]")


@pytest.mark.skipif(not ocr.tesseract_available(), reason="tesseract binary not installed")
async def test_scanned_circular_is_ocrd_with_confidence_recorded(corpus: dict[str, Any]) -> None:
    version = await _version("C-2026-11", "1")
    assert version.parser == "pypdf+tesseract"
    assert version.ocr_min_confidence is not None and version.ocr_min_confidence >= 0.8
    assert version.ocr_page_confidence and "1" in version.ocr_page_confidence
    async with get_sessionmaker()() as session:
        chunks = list((await session.execute(select(Chunk).where(Chunk.version_id == version.id))).scalars())
    amendment = next(c for c in chunks if "2" in c.covered_paths)
    assert "2(b)" in amendment.covered_paths
    assert "within 3 hours of recognition" in amendment.text
    assert amendment.bbox and amendment.bbox["boxes"][0]["page"] == 1


async def test_statuses_and_confirmed_links_follow_metadata(corpus: dict[str, Any]) -> None:
    assert (await _version("P-ICU-07", "2")).status == VersionStatus.superseded
    assert (await _version("P-ICU-07", "3")).status == VersionStatus.approved
    assert (await _version("C-2026-14", "1")).status == VersionStatus.draft
    confirmed = await scalar(
        "SELECT count(*) FROM supersessions WHERE confirmed AND target_section_path IN ('4.2', '5.3')"
    )
    assert confirmed == 2


async def test_amendment_suggestions_are_detected_from_circular_text(corpus: dict[str, Any]) -> None:
    draft = await _version("C-2026-14", "1")
    async with get_sessionmaker()() as session:
        links = list(
            (await session.execute(select(Supersession).where(Supersession.source_version_id == draft.id))).scalars()
        )
    assert {(link.target_section_path, link.suggested, link.confirmed) for link in links} == {
        ("3.1", True, False),
        ("3.2", True, False),
    }


async def test_ingest_time_conflicts_skip_branch_overrides_and_superseded_text(
    corpus: dict[str, Any],
) -> None:
    # A Riverside-only SOP deliberately differs from the network protocol: never a "conflict".
    overrides = await scalar("""
        SELECT count(*) FROM conflicts c
        JOIN chunks a ON a.id = c.chunk_a_id JOIN chunks b ON b.id = c.chunk_b_id
        JOIN document_versions va ON va.id = a.version_id JOIN documents da ON da.id = va.document_id
        JOIN document_versions vb ON vb.id = b.version_id JOIN documents db ON db.id = vb.document_id
        WHERE da.applies_to_all_branches <> db.applies_to_all_branches
    """)
    assert overrides == 0
    # Superseded clauses (P-ICU-07 §4.2, P-ED-01 §5.3) are never compared.
    superseded = await scalar("""
        SELECT count(*) FROM conflicts c JOIN chunks x ON x.id IN (c.chunk_a_id, c.chunk_b_id)
        JOIN document_versions v ON v.id = x.version_id JOIN documents d ON d.id = v.document_id
        WHERE (d.doc_code = 'P-ICU-07' AND x.section_path = '4.2') OR (d.doc_code = 'P-ED-01' AND x.section_path = '5.3')
    """)
    assert superseded == 0


async def test_ingestion_is_audited(corpus: dict[str, Any]) -> None:
    assert await scalar("SELECT count(*) FROM audit_events WHERE action = 'version.ingested'") == 11


async def test_sql_and_python_effective_version_rules_agree(corpus: dict[str, Any], services: Services) -> None:
    """The retrieval SQL pre-filter and the independent Python authority filter must match exactly."""
    as_of = services.settings.today()
    async with get_sessionmaker()() as session:
        all_ids = list((await session.execute(select(Chunk.id))).scalars())
        branches = [None, *[b.id for b in (await session.execute(select(Branch))).scalars()]]
        for branch in branches:
            sql_ids = set(
                (
                    await session.execute(
                        text(ELIGIBLE_CTE + " SELECT id FROM eligible"), {"as_of": as_of, "branch_id": branch}
                    )
                ).scalars()
            )
            candidates = await load_candidates(session, all_ids, as_of)
            ctx = await authority.load_context(session, as_of, branch)
            kept, _ = authority.filter_eligible(list(candidates.values()), ctx)
            assert {c.chunk_id for c in kept} == sql_ids, f"branch {branch}"
            # Never eligible: superseded P-ICU-07 §4.2, P-ED-01 §5.3, old versions, the draft circular.
            labels = {(c.doc_code, c.version_label, c.section_path) for c in kept}
            assert ("P-ICU-07", "3", "4.2") not in labels
            assert ("P-ED-01", "2", "5.3") not in labels
            assert not any(code == "C-2026-14" for code, _, _ in labels)
            assert not any((code, v) in {("P-ICU-07", "2"), ("P-ED-01", "1")} for code, v, _ in labels)


async def test_reingest_is_idempotent(corpus: dict[str, Any], services: Services) -> None:
    from app.services.ingestion.pipeline import ingest_version

    draft = await _version("C-2026-14", "1")
    before = await scalar("SELECT count(*) FROM chunks WHERE version_id = :v", v=draft.id)
    async with get_sessionmaker()() as session:
        report = await ingest_version(session, services, draft.id)
    assert report.status == IngestStatus.ready
    assert await scalar("SELECT count(*) FROM chunks WHERE version_id = :v", v=draft.id) == before


async def test_unknown_version_raises(services: Services) -> None:
    from app.services.ingestion.pipeline import ingest_version

    async with get_sessionmaker()() as session:
        with pytest.raises(ValueError):
            await ingest_version(session, services, uuid.uuid4())
