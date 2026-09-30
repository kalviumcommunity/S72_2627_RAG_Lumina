from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ServicesDep
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import has_role
from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion
from app.models.enums import Role, VersionStatus
from app.models.supersession import Supersession
from app.models.user import User
from app.schemas.source import AmendsRef, OutlineItem, SourceOut, SupersededByRef
from app.services.ingestion.supersession import (
    SupersessionInfo,
    VersionInfo,
    current_version,
    is_superseded,
)

router = APIRouter(prefix="/sources", tags=["sources"])

CLINICIAN_VISIBLE = {VersionStatus.approved, VersionStatus.superseded, VersionStatus.retired}


def _check_visible(user: User, version: DocumentVersion) -> None:
    if version.status not in CLINICIAN_VISIBLE and not has_role(user.role, Role.author):
        # Clinicians never see drafts — answer "not found" rather than revealing it exists.
        raise NotFoundError("Source not found")


@router.get("/{chunk_id}", response_model=SourceOut)
async def get_source(chunk_id: uuid.UUID, user: CurrentUser, session: DbSession, services: ServicesDep) -> SourceOut:
    chunk = await session.get(Chunk, chunk_id)
    if chunk is None:
        raise NotFoundError("Source not found")
    version = await session.get(DocumentVersion, chunk.version_id)
    assert version is not None
    _check_visible(user, version)
    document = await session.get(Document, version.document_id)
    assert document is not None
    as_of = services.settings.today()

    outline_rows = list(
        (await session.execute(select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.ordinal))).scalars()
    )
    ordinals = [c.id for c in outline_rows]
    index = ordinals.index(chunk.id)

    all_versions = list(
        (await session.execute(select(DocumentVersion).where(DocumentVersion.document_id == document.id))).scalars()
    )
    infos = [VersionInfo(v.id, v.document_id, v.status, v.effective_from, v.approved_at) for v in all_versions]
    current = current_version(infos, as_of)

    # Links amending this document (which may supersede the opened clause).
    incoming = list(
        (await session.execute(select(Supersession).where(Supersession.target_document_id == document.id))).scalars()
    )
    superseded_by: list[SupersededByRef] = []
    for link in incoming:
        source_version = await session.get(DocumentVersion, link.source_version_id)
        if source_version is None:
            continue
        info = SupersessionInfo(
            link.source_version_id,
            source_version.status,
            link.target_document_id,
            link.target_section_path,
            link.effective_from,
            link.confirmed,
        )
        if is_superseded(document.id, chunk.covered_paths or [chunk.section_path], [info], as_of):
            source_doc = await session.get(Document, source_version.document_id)
            assert source_doc is not None
            superseded_by.append(
                SupersededByRef(
                    doc_code=source_doc.doc_code,
                    title=source_doc.title,
                    version=source_version.version_label,
                    version_id=source_version.id,
                    section_path=link.target_section_path,
                    effective_from=link.effective_from,
                )
            )

    outgoing = list(
        (
            await session.execute(
                select(Supersession, Document.doc_code)
                .join(Document, Document.id == Supersession.target_document_id)
                .where(Supersession.source_version_id == version.id, Supersession.confirmed.is_(True))
            )
        ).all()
    )
    amends = [AmendsRef(doc_code=code, section_path=s.target_section_path) for s, code in outgoing]

    newer: SupersededByRef | None = None
    if current is not None and current.id != version.id:
        newer_version = next(v for v in all_versions if v.id == current.id)
        newer = SupersededByRef(
            doc_code=document.doc_code,
            title=document.title,
            version=newer_version.version_label,
            version_id=newer_version.id,
            section_path=None,
            effective_from=newer_version.effective_from,
        )

    return SourceOut(
        chunk_id=chunk.id,
        version_id=version.id,
        document_id=document.id,
        doc_code=document.doc_code,
        title=document.title,
        doc_type=document.doc_type,
        version=version.version_label,
        status=version.status,
        is_current=current is not None and current.id == version.id,
        effective_from=version.effective_from,
        review_due=version.review_due,
        section_path=chunk.section_path,
        covered_paths=list(chunk.covered_paths or []),
        heading=chunk.heading,
        text=chunk.text,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        bbox=chunk.bbox,
        is_table=chunk.is_table,
        mime_type=version.mime_type,
        file_url=f"/api/v1/sources/{version.id}/file",
        ocr_min_confidence=version.ocr_min_confidence,
        neighbours={
            "previous": ordinals[index - 1] if index > 0 else None,
            "next": ordinals[index + 1] if index + 1 < len(ordinals) else None,
        },
        outline=[
            OutlineItem(
                chunk_id=c.id,
                section_path=c.section_path,
                heading=c.heading,
                text=c.text,
                is_table=c.is_table,
                page_start=c.page_start,
            )
            for c in outline_rows
            if not (c.is_table and " — row " in c.heading)  # per-row index chunks are search aids only
        ],
        superseded_by=superseded_by,
        amends=amends,
        newer_version=newer,
    )


@router.get("/{version_id}/file")
async def get_source_file(version_id: uuid.UUID, user: CurrentUser, session: DbSession) -> FileResponse:
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        raise NotFoundError("File not found")
    _check_visible(user, version)
    path = Path(version.file_path)
    if not await asyncio.to_thread(path.exists):
        raise NotFoundError("File missing from storage")
    if version.status == VersionStatus.retired and not has_role(user.role, Role.author):
        raise ForbiddenError("This version has been retired")
    return FileResponse(
        path,
        media_type=version.mime_type,
        filename=version.original_filename,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
        content_disposition_type="inline",
    )
