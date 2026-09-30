"""Ingestion pipeline: parse → OCR → chunk → embed → index → supersession suggestions → audit.

`ingest_version` runs when a version is uploaded (and again on demand). `after_approval` runs when
a version is approved: it retires older versions that it replaces and runs ingest-time conflict
detection against other current documents.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.conflict import Conflict
from app.models.document import Document, DocumentVersion
from app.models.enums import DetectedBy, IngestStatus, VersionStatus
from app.models.supersession import Supersession
from app.services import audit
from app.services.ingestion import supersession as supersession_rules
from app.services.ingestion.chunker import ChunkDraft, chunk_document
from app.services.ingestion.conflict import judge_conflict
from app.services.ingestion.metadata import MetadataInput, extract_metadata, metadata_mismatch_warnings
from app.services.ingestion.parser import ParsedDocument, parse_file
from app.services.registry import Services
from app.services.retrieval.eligibility import eligible_cte
from app.services.retrieval.terms import term_stats
from app.services.retrieval.vector import vector_literal
from app.services.safety import pii_redaction

log = get_logger(__name__)

MIME_BY_SUFFIX = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".htm": "text/html",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_file(
    storage_dir: Path, document_id: uuid.UUID, version_id: uuid.UUID, source: Path | bytes, suffix: str
) -> Path:
    target_dir = storage_dir / str(document_id) / str(version_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"original{suffix.lower()}"
    if isinstance(source, bytes):
        target.write_bytes(source)
    else:
        shutil.copyfile(source, target)
    return target


@dataclass
class IngestReport:
    version_id: uuid.UUID
    status: str
    chunks: int = 0
    parser: str | None = None
    ocr_min_confidence: float | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    suggestions: int = 0
    error: str | None = None


async def ingest_version(
    session: AsyncSession,
    services: Services,
    version_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> IngestReport:
    settings = services.settings
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"version {version_id} not found")
    document = await session.get(Document, version.document_id)
    assert document is not None
    version.ingest_status = IngestStatus.processing
    version.ingest_error = None
    await session.commit()

    try:
        parsed: ParsedDocument = await asyncio.to_thread(
            parse_file,
            Path(version.file_path),
            ocr_languages=settings.ocr_languages,
            ocr_dpi=settings.ocr_dpi,
            docling_enabled=settings.docling_enabled,
        )
        drafts: list[ChunkDraft] = chunk_document(
            parsed, doc_code=document.doc_code, version_label=version.version_label
        )
        if not drafts:
            raise ValueError("No text chunks could be produced from this document")
        vectors = await asyncio.to_thread(services.embedder.embed_documents, [d.embedding_text for d in drafts])

        warnings: list[dict[str, Any]] = list(parsed.warnings)
        submitted = MetadataInput(
            doc_code=document.doc_code,
            title=document.title,
            doc_type=document.doc_type,
            version_label=version.version_label,
            effective_from=version.effective_from,
            review_due=version.review_due,
        )
        warnings += metadata_mismatch_warnings(submitted, extract_metadata(parsed.full_text))
        low_pages = {p: c for p, c in parsed.ocr_page_confidence.items() if c < settings.ocr_min_confidence}
        if low_pages:
            warnings.append(
                {
                    "code": "ocr_low_confidence",
                    "pages": sorted(low_pages),
                    "message": (
                        f"OCR confidence below {settings.ocr_min_confidence:.0%} on page(s) "
                        f"{', '.join(str(p) for p in sorted(low_pages))}. An author must check the extracted text "
                        "against the original and acknowledge before approval."
                    ),
                }
            )

        await session.execute(delete(Chunk).where(Chunk.version_id == version.id))
        for draft, vector in zip(drafts, vectors, strict=True):
            session.add(
                Chunk(
                    version_id=version.id,
                    ordinal=draft.ordinal,
                    section_path=draft.section_path,
                    covered_paths=draft.covered_paths,
                    heading=draft.heading[:500],
                    text=draft.text,
                    context_header=draft.context_header[:600],
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    char_start=draft.char_start,
                    char_end=draft.char_end,
                    bbox=draft.bbox,
                    is_table=draft.is_table,
                    token_count=draft.token_count,
                    embedding=vector,
                )
            )
        version.parser = parsed.parser
        version.page_count = parsed.page_count
        version.ocr_min_confidence = parsed.ocr_min_confidence
        version.ocr_page_confidence = {str(k): v for k, v in parsed.ocr_page_confidence.items()} or None
        version.parse_warnings = warnings
        if low_pages:  # a (re-)parse with weak OCR always needs a fresh human check
            version.ocr_acknowledged_at = None
            version.ocr_acknowledged_by = None
        suggestions = await suggest_supersessions(session, document, version, parsed.full_text)
        version.ingest_status = IngestStatus.ready
        await audit.record(
            session,
            action="version.ingested",
            entity_type="document_version",
            entity_id=version.id,
            actor_user_id=actor_user_id,
            payload={
                "doc_code": document.doc_code,
                "version": version.version_label,
                "chunks": len(drafts),
                "parser": parsed.parser,
                "ocr_min_confidence": parsed.ocr_min_confidence,
                "warnings": [w.get("code") for w in warnings],
                "supersession_suggestions": suggestions,
            },
        )
        await session.commit()
        # New words are never names, and new passages change which query terms are "specific".
        term_stats.add(f"{d.heading}\n{d.text}" for d in drafts)
        pii_redaction.add_vocabulary(
            {w for d in drafts for w in re.findall(r"[A-Za-z][A-Za-z-]{1,}", f"{d.heading} {d.text}")}
        )
        log.info(
            "version_ingested",
            doc_code=document.doc_code,
            version=version.version_label,
            chunks=len(drafts),
            parser=parsed.parser,
        )
        return IngestReport(
            version.id, "ready", len(drafts), parsed.parser, parsed.ocr_min_confidence, warnings, suggestions
        )
    except Exception as exc:
        await session.rollback()
        version = await session.get(DocumentVersion, version_id)
        assert version is not None
        version.ingest_status = IngestStatus.failed
        version.ingest_error = f"{type(exc).__name__}: {exc}"[:2000]
        await audit.record(
            session,
            action="version.ingest_failed",
            entity_type="document_version",
            entity_id=version.id,
            actor_user_id=actor_user_id,
            payload={"error": version.ingest_error},
        )
        await session.commit()
        log.warning("version_ingest_failed", version_id=str(version_id), error_type=type(exc).__name__)
        return IngestReport(version_id, "failed", error=version.ingest_error)


async def suggest_supersessions(
    session: AsyncSession, document: Document, version: DocumentVersion, full_text: str
) -> int:
    codes = {code: doc_id for code, doc_id in await session.execute(select(Document.doc_code, Document.id))}
    created = 0
    for suggestion in supersession_rules.detect_references(full_text, codes.keys(), document.doc_code):
        target_id = codes[suggestion.target_doc_code]
        exists = await session.execute(
            select(Supersession.id).where(
                Supersession.source_version_id == version.id,
                Supersession.target_document_id == target_id,
                Supersession.target_section_path.is_(None)
                if suggestion.target_section_path is None
                else Supersession.target_section_path == suggestion.target_section_path,
            )
        )
        if exists.first():
            continue
        session.add(
            Supersession(
                source_version_id=version.id,
                target_document_id=target_id,
                target_section_path=suggestion.target_section_path,
                effective_from=version.effective_from,
                evidence=suggestion.evidence,
                note="Suggested automatically from the document text; needs approver confirmation.",
                suggested=True,
                confirmed=False,
            )
        )
        created += 1
    return created


async def refresh_version_statuses(session: AsyncSession, document_id: uuid.UUID, as_of: Any) -> list[uuid.UUID]:
    """Mark approved versions that are no longer current (a newer approved version is effective)."""
    versions = list(
        (await session.execute(select(DocumentVersion).where(DocumentVersion.document_id == document_id))).scalars()
    )
    infos = [
        supersession_rules.VersionInfo(v.id, v.document_id, v.status, v.effective_from, v.approved_at) for v in versions
    ]
    current = supersession_rules.current_version(infos, as_of)
    changed: list[uuid.UUID] = []
    if current is None:
        return changed
    for v in versions:
        if v.status == VersionStatus.approved and v.id != current.id and v.effective_from <= current.effective_from:
            v.status = VersionStatus.superseded
            changed.append(v.id)
    return changed


_SIMILAR_SQL = text(
    eligible_cte(branch_filter=False)  # noqa: S608  static SQL; values are bound parameters
    + """
SELECT c.id, c.text, d.doc_code, c.section_path, 1 - (c.embedding <=> CAST(:qvec AS vector)) AS similarity,
       d.department_id
FROM chunks c
JOIN document_versions v ON v.id = c.version_id
JOIN documents d ON d.id = v.document_id
WHERE c.id IN (SELECT id FROM eligible) AND d.id <> :document_id AND c.embedding IS NOT NULL
  -- a branch-specific document deliberately overrides network-wide ones: not a conflict
  AND d.applies_to_all_branches = :applies_to_all
  AND (d.department_id IS NOT DISTINCT FROM :department_id
       OR 1 - (c.embedding <=> CAST(:qvec AS vector)) >= :cross_dept_similarity)
ORDER BY c.embedding <=> CAST(:qvec AS vector)
LIMIT 5
"""
)

# Chunks of one version that are themselves eligible (current, not superseded) — any branch.
_ELIGIBLE_OF_VERSION_SQL = text(
    eligible_cte(branch_filter=False)  # noqa: S608  static SQL; values are bound parameters
    + "\nSELECT id FROM eligible WHERE id IN (SELECT id FROM chunks WHERE version_id = :version_id)"
)


async def detect_ingest_conflicts(
    session: AsyncSession, services: Services, version_id: uuid.UUID, *, cross_dept_similarity: float = 0.88
) -> int:
    """Compare each chunk of a newly approved version with the top-5 similar current chunks elsewhere."""
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        return 0
    document = await session.get(Document, version.document_id)
    assert document is not None
    as_of = services.settings.today()
    eligible_ids: set[uuid.UUID] = set(
        (
            await session.execute(
                _ELIGIBLE_OF_VERSION_SQL, {"as_of": as_of, "branch_id": None, "version_id": version_id}
            )
        ).scalars()
    )
    chunks = [
        c
        for c in (await session.execute(select(Chunk).where(Chunk.version_id == version_id))).scalars()
        if c.id in eligible_ids  # superseded clauses are never compared
    ]
    created = 0
    for chunk in chunks:
        if chunk.embedding is None:
            continue
        rows = await session.execute(
            _SIMILAR_SQL,
            {
                "qvec": vector_literal(list(chunk.embedding)),
                "as_of": as_of,
                "branch_id": None,
                "document_id": document.id,
                "department_id": document.department_id,
                "applies_to_all": document.applies_to_all_branches,
                "cross_dept_similarity": cross_dept_similarity,
            },
        )
        for row in rows:
            finding = await judge_conflict(
                services.llm,
                f"{document.doc_code} §{chunk.section_path}",
                chunk.text,
                f"{row.doc_code} §{row.section_path}",
                row.text,
            )
            if not finding.contradicts or finding.confidence < services.settings.conflict_min_confidence:
                continue
            a, b = sorted([chunk.id, row.id], key=str)
            exists = await session.execute(
                select(Conflict.id).where(Conflict.chunk_a_id == a, Conflict.chunk_b_id == b)
            )
            if exists.first():
                continue
            conflict = Conflict(
                chunk_a_id=a,
                chunk_b_id=b,
                detected_by=DetectedBy.ingest,
                description=finding.description,
                confidence=finding.confidence,
                owner_user_id=document.owner_user_id,
            )
            session.add(conflict)
            await session.flush()
            await audit.record(
                session,
                action="conflict.detected",
                entity_type="conflict",
                entity_id=conflict.id,
                payload={
                    "detected_by": "ingest",
                    "chunks": [str(a), str(b)],
                    "confidence": finding.confidence,
                },
            )
            created += 1
    await session.commit()
    return created


async def after_approval(session: AsyncSession, services: Services, version_id: uuid.UUID) -> dict[str, Any]:
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        return {}
    if version.ingest_status != IngestStatus.ready:
        await ingest_version(session, services, version_id)
    changed = await refresh_version_statuses(session, version.document_id, services.settings.today())
    for vid in changed:
        await audit.record(
            session,
            action="version.superseded",
            entity_type="document_version",
            entity_id=vid,
            payload={"by_version": str(version_id)},
        )
    await session.commit()
    conflicts = await detect_ingest_conflicts(session, services, version_id)
    return {
        "superseded_versions": [str(v) for v in changed],
        "conflicts": conflicts,
        "at": datetime.now(UTC).isoformat(),
    }
