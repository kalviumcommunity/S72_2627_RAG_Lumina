"""Document lifecycle, approval gate, supersession and audit (M6 acceptance)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services import jobs
from app.services.ingestion import ocr
from tests.integration.conftest import ADMIN, APPROVER, AUTHOR, CLINICIAN, login

HEPARIN_Q = "What is the heparin infusion nomogram rate change for aPTT above 100?"

NEW_CIRCULAR = b"""# C-2026-21 Circular: Second Heparin Nomogram Amendment

> SYNTHETIC - FOR DEMO ONLY. Test fixture.

| Field | Value |
|---|---|
| Circular number | C-2026-21 |
| Version | 1 |
| Effective from | 2026-09-20 |

## 1 Background

A further review asked for a longer pause when the aPTT is very high, so the committee approved a revised
step for supra-therapeutic results as set out in section 2 of this circular, which applies network-wide.

## 2 Amendment

In partial modification of P-ICU-07 \xc2\xa74.2 (Heparin Infusion Protocol), the nomogram is replaced as below.

| aPTT (seconds) | Infusion action |
|---|---|
| Above 100 | Stop the infusion for 90 minutes, then restart at a rate reduced by 3 units/kg/h |
"""


async def ask(client: httpx.AsyncClient, question: str = HEPARIN_Q) -> dict[str, Any]:
    r = await client.post("/api/v1/query", json={"question": question}, headers=await login(client, CLINICIAN))
    assert r.status_code == 200, r.text
    return r.json()


async def find_document(client: httpx.AsyncClient, code: str) -> dict[str, Any]:
    docs = (await client.get("/api/v1/documents", params={"q": code}, headers=await login(client, AUTHOR))).json()
    return next(d for d in docs if d["doc_code"] == code)


async def upload(client: httpx.AsyncClient, content: bytes, filename: str, **fields: str) -> httpx.Response:
    form = {
        "doc_code": "C-2026-21",
        "title": "Second Heparin Nomogram Amendment",
        "doc_type": "circular",
        "version_label": "1",
        "effective_from": "2026-09-20",
        "department_code": "ICU",
        **fields,
    }
    return await client.post(
        "/api/v1/documents",
        data=form,
        files={"file": (filename, content, "text/markdown")},
        headers=await login(client, AUTHOR),
    )


async def test_approving_an_amending_circular_changes_the_answer(
    client: httpx.AsyncClient, corpus: dict[str, Any]
) -> None:
    approver = await login(client, APPROVER)

    # 1. Retire C-2026-09: its amendment stops applying and P-ICU-07 §4.2 is current again.
    circ = await find_document(client, "C-2026-09")
    r = await client.post(
        f"/api/v1/documents/{circ['id']}/versions/{circ['versions'][0]['id']}/retire", headers=approver
    )
    assert r.status_code == 200
    before = await ask(client)
    assert before["citations"][0]["doc_code"] == "P-ICU-07" and before["citations"][0]["section_path"] == "4.2"
    assert "60 minutes" in before["answer"]

    # 2. Upload a new circular: ingested inline, supersession suggested, but still a draft.
    r = await upload(client, NEW_CIRCULAR, "C-2026-21.md")
    assert r.status_code == 201, r.text
    created = r.json()
    await jobs.drain_inline()
    detail = (await client.get(f"/api/v1/documents/{created['document_id']}", headers=approver)).json()
    version = detail["versions"][0]
    assert version["ingest_status"] == "ready" and version["status"] == "draft" and version["chunk_count"] >= 3
    (link,) = detail["supersessions_out"]
    assert (link["target_doc_code"], link["target_section_path"], link["confirmed"]) == (
        "P-ICU-07",
        "4.2",
        False,
    )
    assert link["hides_sections"] == ["4.2"]
    unchanged = await ask(client)
    assert all(c["doc_code"] != "C-2026-21" for c in unchanged["citations"] + unchanged["sources"])

    # 3. Authors cannot approve; approvers can (confirming the suggested link at the same time).
    url = f"/api/v1/documents/{created['document_id']}/versions/{created['version_id']}/approve"
    assert (await client.post(url, headers=await login(client, AUTHOR))).status_code == 403
    r = await client.post(url, json={"confirm_suggested_supersessions": True}, headers=approver)
    assert r.status_code == 200, r.text
    assert r.json()["details"]["confirmed_links"] == 1
    await jobs.drain_inline()

    # 4. Within one ingest cycle the answer now comes from the new circular.
    after = await ask(client)
    assert after["citations"][0]["doc_code"] == "C-2026-21"
    assert after["citations"][0]["supersedes"] == {"doc_code": "P-ICU-07", "section_path": "4.2"}
    assert "90 minutes" in after["answer"] and "60 minutes" not in after["answer"]


async def test_upload_validation(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    dup = await upload(
        client,
        (Path(__file__).parents[3] / "sample_corpus/drug_guidelines/DG-02_high_alert_medications_v2.md").read_bytes(),
        "dg02.md",
        doc_code="DG-02",
        doc_type="drug_guideline",
        version_label="9",
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_file"
    bad = await upload(client, b"# x\n\n## 1 A\n\nbody text", "x.md", doc_code="not a code")
    assert bad.status_code == 422
    wrong_type = await upload(client, b"# y\n\n## 1 A\n\nother body", "y.exe")
    assert wrong_type.status_code == 422
    clash = await upload(
        client,
        b"# z\n\n## 1 A\n\nyet another body",
        "z.md",
        doc_code="P-ICU-07",
        doc_type="protocol",
        version_label="3",
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "duplicate_version"


@pytest.mark.skipif(not ocr.tesseract_available(), reason="tesseract binary not installed")
async def test_low_ocr_confidence_blocks_approval_until_acknowledged(
    client: httpx.AsyncClient, corpus: dict[str, Any], tmp_path: Path
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (1240, 600), 255)
    ImageDraw.Draw(image).text(
        (60, 60), "1 PURPOSE\nFaint scanned test page for OCR gating.", fill=90, font=ImageFont.load_default()
    )
    pdf = tmp_path / "faint.pdf"
    image.save(pdf, "PDF", resolution=150.0)

    settings = get_settings()
    previous, settings.ocr_min_confidence = settings.ocr_min_confidence, 0.999
    try:
        r = await client.post(
            "/api/v1/documents",
            data={
                "doc_code": "SOP-OCR-01",
                "title": "OCR gate test",
                "doc_type": "sop",
                "version_label": "1",
                "effective_from": "2026-09-01",
            },
            files={"file": ("faint.pdf", pdf.read_bytes(), "application/pdf")},
            headers=await login(client, AUTHOR),
        )
        assert r.status_code == 201, r.text
        await jobs.drain_inline()
    finally:
        settings.ocr_min_confidence = previous
    ids = r.json()
    base = f"/api/v1/documents/{ids['document_id']}/versions/{ids['version_id']}"
    detail = (await client.get(f"/api/v1/documents/{ids['document_id']}", headers=await login(client, AUTHOR))).json()
    assert detail["versions"][0]["needs_ocr_acknowledgement"] is True
    blocked = await client.post(f"{base}/approve", headers=await login(client, APPROVER))
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "ocr_acknowledgement_required"
    assert (await client.post(f"{base}/acknowledge-ocr", headers=await login(client, AUTHOR))).status_code == 200
    assert (await client.post(f"{base}/approve", headers=await login(client, APPROVER))).status_code == 200


async def test_supersession_endpoints(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    approver = await login(client, APPROVER)
    pending = (await client.get("/api/v1/supersessions", params={"confirmed": "false"}, headers=approver)).json()
    dg01 = [p for p in pending if p["target_doc_code"] == "DG-01"]
    assert {p["target_section_path"] for p in dg01} == {"3.1", "3.2"}
    link = dg01[0]
    patched = await client.patch(f"/api/v1/supersessions/{link['id']}", json={"note": "checked"}, headers=approver)
    assert patched.status_code == 200 and patched.json()["note"] == "checked"
    assert (await client.delete(f"/api/v1/supersessions/{link['id']}", headers=approver)).status_code == 200
    author = await login(client, AUTHOR)
    assert (await client.delete(f"/api/v1/supersessions/{dg01[1]['id']}", headers=author)).status_code == 403


async def test_conflicts_can_be_listed_and_resolved(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    await ask(client, "When should the aPTT be repeated after a heparin rate change?")  # ensures one exists
    author = await login(client, AUTHOR)
    conflicts = (await client.get("/api/v1/conflicts", params={"status": "open"}, headers=author)).json()
    assert conflicts
    first = conflicts[0]
    assert {first["a"]["doc_code"], first["b"]["doc_code"]} == {"P-ICU-07", "DG-02"}
    r = await client.patch(
        f"/api/v1/conflicts/{first['id']}",
        json={"status": "resolved", "resolution_note": "DG-02 to be aligned"},
        headers=author,
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved"


async def test_admin_stats_contacts_reference_and_health(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    admin = await login(client, ADMIN)
    stats = (await client.get("/api/v1/admin/stats", headers=admin)).json()
    assert stats["total_questions"] >= 1
    assert {d["doc_code"] for d in stats["stale_documents"]} >= {"P-HAEM-02", "DG-02"}
    assert stats["documents_awaiting_approval"] >= 1
    contacts = (await client.get("/api/v1/contacts", headers=await login(client, CLINICIAN))).json()
    labels = {c["role_label"] for c in contacts}
    assert "Duty doctor — Central" in labels and "Duty doctor — Riverside" not in labels
    ref = (await client.get("/api/v1/admin/reference-data", headers=await login(client, AUTHOR))).json()
    assert {b["code"] for b in ref["branches"]} == {"CEN", "RIV", "HIL"}
    health = (await client.get("/api/v1/health")).json()
    assert health["checks"]["db"]["ok"] and health["checks"]["db"]["pgvector"]


async def test_audit_log_is_hash_chained_and_append_only(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    admin = await login(client, ADMIN)
    verify = (await client.get("/api/v1/admin/audit/verify", headers=admin)).json()
    assert verify["ok"] and verify["events_checked"] > 10
    events = (await client.get("/api/v1/admin/audit", params={"action": "version."}, headers=admin)).json()
    assert events and all(e["action"].startswith("version.") for e in events)
    csv = await client.get("/api/v1/admin/audit", params={"format": "csv", "limit": 5}, headers=admin)
    assert csv.status_code == 200 and csv.text.startswith("seq,created_at,actor,action")
    async with get_sessionmaker()() as session:
        for statement in (
            "UPDATE audit_events SET action = 'tampered'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(text(statement))
            await session.rollback()
    assert (await client.get("/api/v1/admin/audit/verify", headers=admin)).json()["ok"]
