"""Load the synthetic sample corpus (sample_corpus/metadata.yaml) through the real ingestion pipeline.

Usage (from backend/):  python -m scripts.ingest_sample [--corpus ../sample_corpus] [--no-conflicts]
Idempotent: versions that already exist (same document + label) are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.models import Branch, Department, Document, DocumentVersion, Supersession, User
from app.models.enums import DocType, IngestStatus, VersionStatus
from app.services import audit
from app.services.ingestion.pipeline import (
    MIME_BY_SUFFIX,
    detect_ingest_conflicts,
    ingest_version,
    refresh_version_statuses,
    sha256_bytes,
    store_file,
)
from app.services.registry import get_services, load_corpus_vocabulary

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "sample_corpus"


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


async def load_corpus(corpus: Path, *, detect_conflicts: bool = True, verbose: bool = True) -> dict[str, Any]:
    meta = yaml.safe_load((corpus / "metadata.yaml").read_text(encoding="utf-8"))
    services = get_services()
    settings = services.settings
    summary: dict[str, Any] = {
        "versions_created": 0,
        "versions_skipped": 0,
        "links": 0,
        "conflicts": 0,
        "failed": [],
    }

    def say(message: str) -> None:
        if verbose:
            print(message, flush=True)

    maker = get_sessionmaker()
    async with maker() as session:
        users = {u.email: u for u in (await session.execute(select(User))).scalars()}
        departments = {d.code: d for d in (await session.execute(select(Department))).scalars()}
        branches = {b.code: b for b in (await session.execute(select(Branch))).scalars()}
        if not users:
            raise SystemExit("No users found — run `python -m scripts.seed` first")
        approver: User = users[meta["approver"]]

        for doc_meta in meta["documents"]:
            document = (
                await session.execute(select(Document).where(Document.doc_code == doc_meta["doc_code"]))
            ).scalar_one_or_none()
            if document is None:
                document = Document(
                    doc_code=doc_meta["doc_code"],
                    title=doc_meta["title"],
                    doc_type=DocType(doc_meta["doc_type"]),
                    department_id=departments[doc_meta["department"]].id,
                    owner_user_id=users[doc_meta["owner"]].id,
                    applies_to_all_branches=bool(doc_meta.get("applies_to_all_branches", True)),
                )
                document.branches = [branches[c] for c in doc_meta.get("branches", [])]
                session.add(document)
                await session.commit()

            for v_meta in doc_meta["versions"]:
                label = str(v_meta["label"])
                existing = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == document.id, DocumentVersion.version_label == label
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    summary["versions_skipped"] += 1
                    continue
                source = corpus / v_meta["file"]
                data = source.read_bytes()
                version = DocumentVersion(
                    document_id=document.id,
                    version_label=label,
                    status=VersionStatus.draft,
                    effective_from=_as_date(v_meta["effective_from"]),
                    review_due=_as_date(v_meta["review_due"]) if v_meta.get("review_due") else None,
                    uploaded_by=document.owner_user_id,
                    file_path="pending",
                    original_filename=source.name,
                    mime_type=MIME_BY_SUFFIX.get(source.suffix.lower(), "application/octet-stream"),
                    file_sha256=sha256_bytes(data),
                    ingest_status=IngestStatus.pending,
                    parse_warnings=[],
                )
                session.add(version)
                await session.flush()
                version.file_path = str(store_file(settings.storage_dir, document.id, version.id, data, source.suffix))
                await audit.record(
                    session,
                    action="version.uploaded",
                    entity_type="document_version",
                    entity_id=version.id,
                    actor_user_id=document.owner_user_id,
                    payload={"doc_code": document.doc_code, "version": label, "source": "sample_corpus"},
                )
                await session.commit()

                report = await ingest_version(session, services, version.id, actor_user_id=document.owner_user_id)
                if report.status != "ready":
                    summary["failed"].append(f"{document.doc_code} v{label}: {report.error}")
                    say(f"  ! {document.doc_code} v{label}: ingestion failed — {report.error}")
                    continue
                version = await session.get(DocumentVersion, version.id)
                assert version is not None
                target_status = VersionStatus(v_meta.get("status", "draft"))
                if target_status != VersionStatus.draft:
                    if version.needs_ocr_acknowledgement:
                        version.ocr_acknowledged_by = document.owner_user_id
                        version.ocr_acknowledged_at = datetime.now(UTC)
                    version.approved_by = approver.id
                    version.approved_at = datetime.combine(version.effective_from, time(9, 0), UTC)
                    version.status = target_status
                    if target_status == VersionStatus.retired:
                        version.retired_at = datetime.now(UTC)
                    await audit.record(
                        session,
                        action=f"version.{target_status.value}",
                        entity_type="document_version",
                        entity_id=version.id,
                        actor_user_id=approver.id,
                        payload={"doc_code": document.doc_code, "version": label, "source": "sample_corpus"},
                    )
                await session.commit()
                summary["versions_created"] += 1
                ocr = f", OCR {report.ocr_min_confidence:.0%}" if report.ocr_min_confidence is not None else ""
                say(
                    f"  + {document.doc_code} v{label}: {report.chunks} chunks via {report.parser}{ocr} → {target_status.value}"
                )

        # Supersession links declared in metadata.yaml (confirm a matching suggestion if one exists).
        codes = {d.doc_code: d for d in (await session.execute(select(Document))).scalars()}
        for link_meta in meta.get("supersessions", []):
            src_code, src_label = str(link_meta["source"]).split("@", 1)
            src_version = (
                await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == codes[src_code].id,
                        DocumentVersion.version_label == src_label,
                    )
                )
            ).scalar_one()
            target = codes[link_meta["target"]]
            section = str(link_meta["section"]) if link_meta.get("section") is not None else None
            link = (
                await session.execute(
                    select(Supersession).where(
                        Supersession.source_version_id == src_version.id,
                        Supersession.target_document_id == target.id,
                        Supersession.target_section_path.is_(None)
                        if section is None
                        else Supersession.target_section_path == section,
                    )
                )
            ).scalar_one_or_none()
            if link is None:
                link = Supersession(
                    source_version_id=src_version.id,
                    target_document_id=target.id,
                    target_section_path=section,
                    suggested=False,
                    created_by=approver.id,
                    effective_from=_as_date(link_meta.get("effective_from") or src_version.effective_from),
                )
                session.add(link)
            if link_meta.get("confirmed", True) and not link.confirmed:
                link.confirmed = True
                link.confirmed_by = approver.id
                link.confirmed_at = datetime.now(UTC)
                link.note = link_meta.get("note") or link.note
                await session.flush()
                await audit.record(
                    session,
                    action="supersession.confirmed",
                    entity_type="supersession",
                    entity_id=link.id,
                    actor_user_id=approver.id,
                    payload={
                        "source": link_meta["source"],
                        "target": target.doc_code,
                        "section": section,
                        "origin": "sample_corpus",
                    },
                )
                summary["links"] += 1
                say(f"  ↳ {link_meta['source']} supersedes {target.doc_code}" + (f" §{section}" if section else ""))
        await session.commit()

        for document in codes.values():
            await refresh_version_statuses(session, document.id, settings.today())
        await session.commit()

        if detect_conflicts:
            approved = (
                (
                    await session.execute(
                        select(DocumentVersion.id).where(DocumentVersion.status == VersionStatus.approved)
                    )
                )
                .scalars()
                .all()
            )
            for version_id in approved:
                summary["conflicts"] += await detect_ingest_conflicts(session, services, version_id)
            say(f"  ⚠ ingest-time conflict detection: {summary['conflicts']} new conflict(s)")
        await load_corpus_vocabulary(session)
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--no-conflicts", action="store_true", help="skip ingest-time conflict detection")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging("WARNING", json_logs=False)
    init_engine()
    print(f"Loading sample corpus from {args.corpus} (SYNTHETIC — FOR DEMO ONLY); LLM={settings.llm_provider}")
    try:
        summary = await load_corpus(args.corpus, detect_conflicts=not args.no_conflicts)
        print("Done:", {k: v for k, v in summary.items() if v})
        if summary["failed"]:
            raise SystemExit(1)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
