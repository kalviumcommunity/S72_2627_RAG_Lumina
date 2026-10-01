from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApproverUser, AuthorUser, DbSession, ServicesDep
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.branch import Branch
from app.models.chunk import Chunk
from app.models.department import Department
from app.models.document import Document, DocumentVersion
from app.models.enums import DocType, IngestStatus, VersionStatus
from app.models.supersession import Supersession
from app.models.user import User
from app.schemas.document import (
    ActionResult,
    ApproveRequest,
    BranchOut,
    ChunkOut,
    DepartmentOut,
    DocumentDetail,
    DocumentOut,
    ExtractedMetadataOut,
    SupersessionCreate,
    SupersessionOut,
    SupersessionPatch,
    UploadResult,
    UserOut,
    VersionOut,
)
from app.services import audit, jobs
from app.services.ingestion.metadata import MetadataInput, extract_metadata, validate_metadata
from app.services.ingestion.parser import SUPPORTED_EXTENSIONS, ParseError, parse_file
from app.services.ingestion.pipeline import MIME_BY_SUFFIX, refresh_version_statuses, sha256_bytes, store_file
from app.services.ingestion.supersession import VersionInfo, current_version, section_matches

router = APIRouter(tags=["documents"])

INGEST_JOB_TIMEOUT_S = 900  # matches WorkerSettings.job_timeout


# --------------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------------


async def _chunk_counts(session: AsyncSession, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not version_ids:
        return {}
    rows = await session.execute(
        select(Chunk.version_id, func.count()).where(Chunk.version_id.in_(version_ids)).group_by(Chunk.version_id)
    )
    return {vid: n for vid, n in rows.all()}


def _version_out(v: DocumentVersion, current_id: uuid.UUID | None, chunks: dict[uuid.UUID, int]) -> VersionOut:
    out = VersionOut.model_validate(v)
    out.needs_ocr_acknowledgement = v.needs_ocr_acknowledgement
    out.is_current = v.id == current_id
    out.chunk_count = chunks.get(v.id, 0)
    return out


async def _document_out(session: AsyncSession, doc: Document, as_of: date, detail: bool = False) -> DocumentOut:
    versions = sorted(doc.versions, key=lambda v: (v.effective_from, v.created_at), reverse=True)
    current = current_version(
        [VersionInfo(v.id, v.document_id, v.status, v.effective_from, v.approved_at) for v in versions], as_of
    )
    chunks = await _chunk_counts(session, [v.id for v in versions])
    owner = await session.get(User, doc.owner_user_id) if doc.owner_user_id else None
    review_dates = [v.review_due for v in versions if v.status == VersionStatus.approved and v.review_due]
    next_review = min(review_dates) if review_dates else None
    payload = {
        "id": doc.id,
        "doc_code": doc.doc_code,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "department": DepartmentOut.model_validate(doc.department) if doc.department else None,
        "owner": UserOut.model_validate(owner) if owner else None,
        "applies_to_all_branches": doc.applies_to_all_branches,
        "branches": [BranchOut.model_validate(b) for b in doc.branches],
        "versions": [_version_out(v, current.id if current else None, chunks) for v in versions],
        "current_version_id": current.id if current else None,
        "review_overdue": bool(next_review and next_review < as_of),
        "next_review_due": next_review,
    }
    if not detail:
        return DocumentOut(**payload)
    version_ids = [v.id for v in versions]
    out_links = (
        (await session.execute(select(Supersession).where(Supersession.source_version_id.in_(version_ids))))
        .scalars()
        .all()
        if version_ids
        else []
    )
    in_links = (
        (await session.execute(select(Supersession).where(Supersession.target_document_id == doc.id))).scalars().all()
    )
    return DocumentDetail(
        **payload,
        supersessions_out=[await _supersession_out(session, s) for s in out_links],
        supersessions_in=[await _supersession_out(session, s) for s in in_links],
    )


async def _supersession_out(session: AsyncSession, s: Supersession) -> SupersessionOut:
    source_version = await session.get(DocumentVersion, s.source_version_id)
    assert source_version is not None
    source_doc = await session.get(Document, source_version.document_id)
    target_doc = await session.get(Document, s.target_document_id)
    assert source_doc is not None and target_doc is not None
    target_versions = [
        VersionInfo(v.id, v.document_id, v.status, v.effective_from, v.approved_at) for v in target_doc.versions
    ]
    target_current = current_version(target_versions, get_settings().today())
    hides: list[str] = []
    if target_current is not None:
        rows = await session.execute(
            select(Chunk.section_path, Chunk.covered_paths)
            .where(Chunk.version_id == target_current.id)
            .order_by(Chunk.ordinal)
        )
        for path, covered in rows.all():
            hit = any(section_matches(s.target_section_path, p) for p in (covered or [path]))
            if hit and path not in hides:
                hides.append(path)
    return SupersessionOut(
        id=s.id,
        source_version_id=s.source_version_id,
        source_doc_code=source_doc.doc_code,
        source_version_label=source_version.version_label,
        source_status=source_version.status,
        target_document_id=s.target_document_id,
        target_doc_code=target_doc.doc_code,
        target_section_path=s.target_section_path,
        effective_from=s.effective_from,
        note=s.note,
        evidence=s.evidence,
        suggested=s.suggested,
        confirmed=s.confirmed,
        confirmed_at=s.confirmed_at,
        hides_sections=hides,
    )


async def _get_version(session: AsyncSession, document_id: uuid.UUID, version_id: uuid.UUID) -> DocumentVersion:
    version = await session.get(DocumentVersion, version_id)
    if version is None or version.document_id != document_id:
        raise NotFoundError("Document version not found")
    return version


# --------------------------------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    user: AuthorUser,
    session: DbSession,
    services: ServicesDep,
    status: VersionStatus | None = None,
    doc_type: DocType | None = None,
    department_id: uuid.UUID | None = None,
    review_overdue: bool | None = None,
    q: str | None = None,
) -> list[DocumentOut]:
    stmt = select(Document).order_by(Document.doc_code)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if department_id:
        stmt = stmt.where(Document.department_id == department_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Document.doc_code.ilike(like), Document.title.ilike(like)))
    docs = list((await session.execute(stmt)).unique().scalars())
    as_of = services.settings.today()
    out = [await _document_out(session, d, as_of) for d in docs]
    if status:
        out = [d for d in out if any(v.status == status for v in d.versions)]
    if review_overdue is not None:
        out = [d for d in out if d.review_overdue == review_overdue]
    return out


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID, user: AuthorUser, session: DbSession, services: ServicesDep
) -> DocumentOut:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    return await _document_out(session, doc, services.settings.today(), detail=True)


@router.post("/documents/extract-metadata", response_model=ExtractedMetadataOut)
async def extract_from_file(user: AuthorUser, file: Annotated[UploadFile, File()]) -> ExtractedMetadataOut:
    """Pre-fill the upload form from the document header (nothing is stored)."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValidationFailedError(f"Unsupported file type {suffix or '(none)'}")
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailedError(f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise ValidationFailedError("File is empty")

    def read_header() -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"upload{suffix}"
            path.write_bytes(data)
            return parse_file(path, ocr_languages=settings.ocr_languages, ocr_dpi=200).full_text

    # Parsing (and OCR of scanned PDFs) is CPU-bound: run it off the event loop so other requests
    # are not frozen while a scan is read.
    try:
        full_text = await asyncio.to_thread(read_header)
    except ParseError as exc:
        raise ValidationFailedError(f"Could not read the file: {exc}") from exc
    meta = extract_metadata(full_text)
    return ExtractedMetadataOut(**meta.__dict__)


@router.post("/documents", response_model=UploadResult, status_code=201)
async def upload_document(
    user: AuthorUser,
    session: DbSession,
    file: Annotated[UploadFile, File()],
    doc_code: Annotated[str, Form(max_length=40)],
    title: Annotated[str, Form(max_length=300)],
    doc_type: Annotated[DocType, Form()],
    version_label: Annotated[str, Form(max_length=40)],
    effective_from: Annotated[date, Form()],
    review_due: Annotated[date | None, Form()] = None,
    department_code: Annotated[str | None, Form()] = None,
    applies_to_all_branches: Annotated[bool, Form()] = True,
    branch_codes: Annotated[str, Form()] = "",
    change_summary: Annotated[str | None, Form(max_length=2000)] = None,
) -> UploadResult:
    settings = get_settings()
    doc_code = doc_code.strip().upper()
    branches = [b.strip().upper() for b in branch_codes.split(",") if b.strip()]
    errors = validate_metadata(
        MetadataInput(
            doc_code=doc_code,
            title=title,
            doc_type=doc_type,
            version_label=version_label.strip(),
            effective_from=effective_from,
            review_due=review_due,
            applies_to_all_branches=applies_to_all_branches,
            branch_codes=branches,
        )
    )
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        errors.append(f"Unsupported file type {suffix or '(none)'}; allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    if errors:
        raise ValidationFailedError("Upload rejected", details=errors)
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailedError(f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise ValidationFailedError("File is empty")
    digest = sha256_bytes(data)
    duplicate = (
        await session.execute(
            select(DocumentVersion, Document.doc_code).join(Document).where(DocumentVersion.file_sha256 == digest)
        )
    ).first()
    if duplicate:
        raise ConflictError(
            f"This exact file is already stored as {duplicate[1]} v{duplicate[0].version_label}",
            code="duplicate_file",
        )

    document = (await session.execute(select(Document).where(Document.doc_code == doc_code))).scalar_one_or_none()
    created = document is None
    if document is None:
        department = None
        if department_code:
            department = (
                await session.execute(select(Department).where(Department.code == department_code.strip().upper()))
            ).scalar_one_or_none()
            if department is None:
                raise ValidationFailedError(f"Unknown department {department_code}")
        document = Document(
            doc_code=doc_code,
            title=title.strip(),
            doc_type=doc_type,
            department_id=department.id if department else None,
            owner_user_id=user.id,
            applies_to_all_branches=applies_to_all_branches,
        )
        if not applies_to_all_branches:
            found = list((await session.execute(select(Branch).where(Branch.code.in_(branches)))).scalars())
            if len(found) != len(set(branches)):
                raise ValidationFailedError("Unknown branch code")
            document.branches = found
        session.add(document)
        await session.flush()
    elif document.doc_type != doc_type:
        raise ValidationFailedError(f"{doc_code} is a {document.doc_type.value}, not a {doc_type.value}")
    clash = (
        await session.execute(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_label == version_label.strip(),
            )
        )
    ).first()
    if clash:
        raise ConflictError(f"{doc_code} already has a version {version_label}", code="duplicate_version")

    version_id = uuid.uuid4()
    path = store_file(settings.storage_dir, document.id, version_id, data, suffix)
    version = DocumentVersion(
        id=version_id,
        document_id=document.id,
        version_label=version_label.strip(),
        status=VersionStatus.draft,
        effective_from=effective_from,
        review_due=review_due,
        change_summary=change_summary,
        uploaded_by=user.id,
        file_path=str(path),
        original_filename=Path(file.filename or f"upload{suffix}").name[:300],
        mime_type=MIME_BY_SUFFIX.get(suffix, "application/octet-stream"),
        file_sha256=digest,
        ingest_status=IngestStatus.pending,
        parse_warnings=[],
    )
    session.add(version)
    await audit.record(
        session,
        action="version.uploaded",
        entity_type="document_version",
        entity_id=version_id,
        actor_user_id=user.id,
        payload={
            "doc_code": doc_code,
            "version": version.version_label,
            "sha256": digest,
            "new_document": created,
        },
    )
    await session.commit()
    mode = await jobs.enqueue("ingest_document", str(version_id), str(user.id))
    return UploadResult(
        document_id=document.id,
        version_id=version_id,
        ingest_status=IngestStatus.pending,
        created_document=created,
        job=mode,
    )


@router.get("/documents/{document_id}/versions/{version_id}/chunks", response_model=list[ChunkOut])
async def version_chunks(
    document_id: uuid.UUID, version_id: uuid.UUID, user: AuthorUser, session: DbSession
) -> list[Chunk]:
    await _get_version(session, document_id, version_id)
    rows = await session.execute(select(Chunk).where(Chunk.version_id == version_id).order_by(Chunk.ordinal))
    return list(rows.scalars())


@router.post("/documents/{document_id}/versions/{version_id}/acknowledge-ocr", response_model=ActionResult)
async def acknowledge_ocr(
    document_id: uuid.UUID, version_id: uuid.UUID, user: AuthorUser, session: DbSession
) -> ActionResult:
    version = await _get_version(session, document_id, version_id)
    if not version.needs_ocr_acknowledgement:
        return ActionResult(message="No OCR warnings need acknowledgement")
    version.ocr_acknowledged_by = user.id
    version.ocr_acknowledged_at = datetime.now(UTC)
    await audit.record(
        session,
        action="version.ocr_acknowledged",
        entity_type="document_version",
        entity_id=version.id,
        actor_user_id=user.id,
        payload={"ocr_min_confidence": version.ocr_min_confidence},
    )
    await session.commit()
    return ActionResult(message="OCR warnings acknowledged")


@router.post("/documents/{document_id}/versions/{version_id}/reingest", response_model=ActionResult)
async def reingest(document_id: uuid.UUID, version_id: uuid.UUID, user: AuthorUser, session: DbSession) -> ActionResult:
    version = await _get_version(session, document_id, version_id)
    if version.status != VersionStatus.draft:
        raise ConflictError("Only draft versions can be re-processed")
    # Two concurrent ingestions of one version would both rewrite its chunks. A job that has been
    # "processing" for longer than the worker's job timeout is treated as dead and may be restarted.
    stale_before = datetime.now(UTC) - timedelta(seconds=INGEST_JOB_TIMEOUT_S)
    if version.ingest_status == IngestStatus.processing and version.updated_at > stale_before:
        raise ConflictError("This version is already being processed", code="ingest_in_progress")
    version.ingest_status = IngestStatus.pending
    await session.commit()
    mode = await jobs.enqueue("ingest_document", str(version_id), str(user.id))
    return ActionResult(message="Re-processing started", details={"job": mode})


@router.post("/documents/{document_id}/versions/{version_id}/approve", response_model=ActionResult)
async def approve_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user: ApproverUser,
    session: DbSession,
    services: ServicesDep,
    body: ApproveRequest | None = None,
) -> ActionResult:
    version = await _get_version(session, document_id, version_id)
    if version.status != VersionStatus.draft:
        raise ConflictError(f"Version is {version.status.value}; only drafts can be approved")
    if version.ingest_status != IngestStatus.ready:
        raise ConflictError(f"Version cannot be approved while ingestion is {version.ingest_status.value}")
    if version.needs_ocr_acknowledgement:
        raise ConflictError(
            "OCR warnings must be acknowledged by an author before approval",
            code="ocr_acknowledgement_required",
        )
    now = datetime.now(UTC)
    version.status = VersionStatus.approved
    version.approved_by = user.id
    version.approved_at = now
    confirmed = 0
    if body and body.confirm_suggested_supersessions:
        links = (
            (
                await session.execute(
                    select(Supersession).where(
                        Supersession.source_version_id == version.id, Supersession.confirmed.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        for link in links:
            link.confirmed, link.confirmed_by, link.confirmed_at = True, user.id, now
            await audit.record(
                session,
                action="supersession.confirmed",
                entity_type="supersession",
                entity_id=link.id,
                actor_user_id=user.id,
                payload={"target_section_path": link.target_section_path},
            )
            confirmed += 1
    await session.flush()
    superseded = await refresh_version_statuses(session, document_id, services.settings.today())
    await audit.record(
        session,
        action="version.approved",
        entity_type="document_version",
        entity_id=version.id,
        actor_user_id=user.id,
        payload={
            "version": version.version_label,
            "superseded_versions": [str(v) for v in superseded],
            "confirmed_links": confirmed,
        },
    )
    await session.commit()
    mode = await jobs.enqueue("post_approval", str(version.id))
    return ActionResult(
        message="Version approved and now visible to clinicians"
        if version.effective_from <= services.settings.today()
        else f"Version approved; it becomes current on {version.effective_from.isoformat()}",
        details={
            "superseded_versions": [str(v) for v in superseded],
            "confirmed_links": confirmed,
            "job": mode,
        },
    )


@router.post("/documents/{document_id}/versions/{version_id}/retire", response_model=ActionResult)
async def retire_version(
    document_id: uuid.UUID, version_id: uuid.UUID, user: ApproverUser, session: DbSession
) -> ActionResult:
    version = await _get_version(session, document_id, version_id)
    if version.status == VersionStatus.retired:
        return ActionResult(message="Already retired")
    previous = version.status
    version.status = VersionStatus.retired
    version.retired_at = datetime.now(UTC)
    await audit.record(
        session,
        action="version.retired",
        entity_type="document_version",
        entity_id=version.id,
        actor_user_id=user.id,
        payload={"previous_status": previous.value},
    )
    await session.commit()
    return ActionResult(message="Version retired; it no longer appears in answers")


# --------------------------------------------------------------------------------------------------
# supersessions
# --------------------------------------------------------------------------------------------------


@router.get("/supersessions", response_model=list[SupersessionOut])
async def list_supersessions(
    user: AuthorUser, session: DbSession, confirmed: bool | None = None
) -> list[SupersessionOut]:
    stmt = select(Supersession).order_by(Supersession.created_at.desc())
    if confirmed is not None:
        stmt = stmt.where(Supersession.confirmed.is_(confirmed))
    return [await _supersession_out(session, s) for s in (await session.execute(stmt)).scalars()]


@router.post("/supersessions", response_model=SupersessionOut, status_code=201)
async def create_supersession(body: SupersessionCreate, user: ApproverUser, session: DbSession) -> SupersessionOut:
    source = await session.get(DocumentVersion, body.source_version_id)
    target = await session.get(Document, body.target_document_id)
    if source is None or target is None:
        raise NotFoundError("Source version or target document not found")
    if source.document_id == target.id:
        raise ValidationFailedError("A document cannot supersede itself; upload a new version instead")
    now = datetime.now(UTC)
    link = Supersession(
        source_version_id=source.id,
        target_document_id=target.id,
        target_section_path=(body.target_section_path or None),
        effective_from=body.effective_from or source.effective_from,
        note=body.note,
        suggested=False,
        confirmed=body.confirmed,
        created_by=user.id,
        confirmed_by=user.id if body.confirmed else None,
        confirmed_at=now if body.confirmed else None,
    )
    session.add(link)
    await session.flush()
    await audit.record(
        session,
        action="supersession.created",
        entity_type="supersession",
        entity_id=link.id,
        actor_user_id=user.id,
        payload={"target": target.doc_code, "section": link.target_section_path, "confirmed": link.confirmed},
    )
    await session.commit()
    return await _supersession_out(session, link)


@router.patch("/supersessions/{link_id}", response_model=SupersessionOut)
async def update_supersession(
    link_id: uuid.UUID, body: SupersessionPatch, user: ApproverUser, session: DbSession
) -> SupersessionOut:
    link = await session.get(Supersession, link_id)
    if link is None:
        raise NotFoundError("Supersession link not found")
    changes = body.model_dump(exclude_unset=True)
    if "target_section_path" in changes:
        link.target_section_path = changes["target_section_path"] or None
    if changes.get("effective_from"):
        link.effective_from = changes["effective_from"]
    if "note" in changes:
        link.note = changes["note"]
    if "confirmed" in changes and changes["confirmed"] is not None:
        link.confirmed = bool(changes["confirmed"])
        link.confirmed_by = user.id if link.confirmed else None
        link.confirmed_at = datetime.now(UTC) if link.confirmed else None
    await audit.record(
        session,
        action="supersession.updated",
        entity_type="supersession",
        entity_id=link.id,
        actor_user_id=user.id,
        payload={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return await _supersession_out(session, link)


@router.delete("/supersessions/{link_id}", response_model=ActionResult)
async def reject_supersession(link_id: uuid.UUID, user: ApproverUser, session: DbSession) -> ActionResult:
    link = await session.get(Supersession, link_id)
    if link is None:
        raise NotFoundError("Supersession link not found")
    await audit.record(
        session,
        action="supersession.rejected",
        entity_type="supersession",
        entity_id=link.id,
        actor_user_id=user.id,
        payload={"target_document_id": str(link.target_document_id), "section": link.target_section_path},
    )
    await session.delete(link)
    await session.commit()
    return ActionResult(message="Link removed")
