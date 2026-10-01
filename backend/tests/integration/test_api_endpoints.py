"""Every /api/v1 endpoint, called the way the web app calls it, by the roles that may (and may not) use it.

`test_every_endpoint_is_covered` fails when a route is added without being listed here, so new
endpoints cannot ship untested. The sample corpus is loaded once for the module (real ingestion).
Bugs fixed during the audit have a regression test marked "regression:".
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.services import jobs
from tests.integration.conftest import ADMIN, APPROVER, AUTHOR, CLINICIAN, PHARMACY_AUTHOR, login, scalar

API = "/api/v1"
HEPARIN_Q = "What is the heparin nomogram step for aPTT above 100?"

COVERED: set[tuple[str, str]] = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/auth/config"),
    ("GET", "/api/v1/auth/dev-users"),
    ("POST", "/api/v1/auth/dev-login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/auth/oidc/login"),
    ("GET", "/api/v1/auth/oidc/callback"),
    ("POST", "/api/v1/query"),
    ("POST", "/api/v1/query/stream"),
    ("GET", "/api/v1/query/stream"),
    ("GET", "/api/v1/query/history"),
    ("GET", "/api/v1/sources/{chunk_id}"),
    ("GET", "/api/v1/sources/{version_id}/file"),
    ("GET", "/api/v1/documents"),
    ("GET", "/api/v1/documents/{document_id}"),
    ("POST", "/api/v1/documents/extract-metadata"),
    ("POST", "/api/v1/documents"),
    ("GET", "/api/v1/documents/{document_id}/versions/{version_id}/chunks"),
    ("POST", "/api/v1/documents/{document_id}/versions/{version_id}/acknowledge-ocr"),
    ("POST", "/api/v1/documents/{document_id}/versions/{version_id}/reingest"),
    ("POST", "/api/v1/documents/{document_id}/versions/{version_id}/approve"),
    ("POST", "/api/v1/documents/{document_id}/versions/{version_id}/retire"),
    ("GET", "/api/v1/supersessions"),
    ("POST", "/api/v1/supersessions"),
    ("PATCH", "/api/v1/supersessions/{link_id}"),
    ("DELETE", "/api/v1/supersessions/{link_id}"),
    ("POST", "/api/v1/feedback"),
    ("GET", "/api/v1/feedback/inbox"),
    ("PATCH", "/api/v1/feedback/{feedback_id}"),
    ("GET", "/api/v1/contacts"),
    ("GET", "/api/v1/admin/stats"),
    ("GET", "/api/v1/conflicts"),
    ("PATCH", "/api/v1/conflicts/{conflict_id}"),
    ("GET", "/api/v1/admin/audit"),
    ("GET", "/api/v1/admin/audit/verify"),
    ("GET", "/api/v1/admin/reference-data"),
    ("GET", "/api/v1/admin/overview"),
}

TEST_PROTOCOL = b"""# P-TEST-01 Test Protocol

| Field | Value |
|---|---|
| Document code | P-TEST-01 |
| Version | 1 |
| Effective from | 2026-09-01 |

## 1 Purpose

This synthetic protocol exists only for the endpoint tests and describes nothing clinical at all.

## 2 Steps

Record the observation chart every 4 hours and escalate to the duty doctor when a score reaches 5.
"""


def api_routes() -> set[tuple[str, str]]:
    """(METHOD, path) of every public API operation, read from the OpenAPI schema."""
    from app.main import app

    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(API)
        for method in operations
    }


async def execute(sql: str, **params: Any) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text(sql), params)
        await session.commit()


async def ask(client: httpx.AsyncClient, question: str, email: str = CLINICIAN) -> dict[str, Any]:
    r = await client.post(f"{API}/query", json={"question": question}, headers=await login(client, email))
    assert r.status_code == 200, r.text
    return r.json()


def sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# --- coverage guard ---------------------------------------------------------------------------------


def test_every_endpoint_is_covered() -> None:
    routes = api_routes()
    assert not routes - COVERED, f"endpoints without a test: {sorted(routes - COVERED)}"
    assert not COVERED - routes, f"tests for endpoints that no longer exist: {sorted(COVERED - routes)}"


# --- health & auth ----------------------------------------------------------------------------------


async def test_health_reports_every_dependency(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    r = await client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"]["ok"] and body["checks"]["db"]["chunks"] > 0
    assert body["checks"]["jobs"]["mode"] == "inline"
    assert body["checks"]["llm"]["provider"] == "none"
    assert body["checks"]["models"]["pii_engine"]  # regression: reports the configured engine even before first use


async def test_auth_endpoints(client: httpx.AsyncClient) -> None:
    config = (await client.get(f"{API}/auth/config")).json()
    assert config["dev_auth"] is True and config["oidc_enabled"] is False and config["session_idle_minutes"] > 0

    users = (await client.get(f"{API}/auth/dev-users")).json()
    assert {u["role"] for u in users} == {"clinician", "author", "approver", "admin"}

    assert (await client.post(f"{API}/auth/dev-login", json={"email": "nobody@dhn.example"})).status_code == 401
    headers = await login(client, CLINICIAN)
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    assert me["email"] == CLINICIAN and me["role"] == "clinician"

    refreshed = await client.post(f"{API}/auth/refresh", headers=headers)
    assert refreshed.status_code == 200 and refreshed.json()["access_token"]

    assert (await client.get(f"{API}/auth/me")).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer nonsense"})).status_code == 401
    # SSO is not configured in the demo: both OIDC endpoints say so instead of failing.
    assert (await client.get(f"{API}/auth/oidc/login")).status_code == 404
    assert (await client.get(f"{API}/auth/oidc/callback")).status_code == 404


# --- query ------------------------------------------------------------------------------------------


async def test_query_routes_answer_refuse_clarify_and_out_of_scope(
    client: httpx.AsyncClient, corpus: dict[str, Any]
) -> None:
    answered = await ask(client, HEPARIN_Q)
    assert answered["route"] == "answer" and answered["outcome"] in ("answered", "partial")
    assert answered["citations"] and all(c["supported"] for c in answered["citations"])
    assert set(answered["timings_ms"]) >= {"route", "retrieve", "generate", "verify", "total"}

    refused = await ask(client, "What heparin bolus should I give Mr Ramesh Kumar, 72 kg?")
    assert refused["route"] == "high_risk" and refused["answer"] is None
    assert refused["pii_redacted"] and "Ramesh" not in refused["redacted_question"]
    assert refused["escalation"]["contacts"]

    assert (await ask(client, "what is the capital of france"))["route"] == "out_of_scope"
    assert (await ask(client, "dose?"))["route"] == "clarify"

    headers = await login(client, CLINICIAN)
    assert (await client.post(f"{API}/query", json={"question": "a"}, headers=headers)).status_code == 422
    assert (await client.post(f"{API}/query", json={"question": "x" * 1001}, headers=headers)).status_code == 422
    assert (await client.post(f"{API}/query", json={"question": HEPARIN_Q})).status_code == 401


async def test_query_streams_route_sources_answer_done(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    headers = await login(client, CLINICIAN)
    post = await client.post(f"{API}/query/stream", json={"question": HEPARIN_Q}, headers=headers)
    assert post.status_code == 200 and post.headers["content-type"].startswith("text/event-stream")
    events = sse_events(post.text)
    assert [name for name, _ in events] == ["route", "sources", "answer", "done"]
    assert events[2][1]["query_id"] == events[3][1]["query_id"]

    get = await client.get(f"{API}/query/stream", params={"q": HEPARIN_Q}, headers=headers)
    assert [name for name, _ in sse_events(get.text)] == ["route", "sources", "answer", "done"]
    assert (await client.get(f"{API}/query/stream", params={"q": "x"}, headers=headers)).status_code == 422


async def test_history_lists_own_redacted_questions(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    await ask(client, "Does Tazocin need AMS approval?")
    headers = await login(client, CLINICIAN)
    items = (await client.get(f"{API}/query/history", params={"limit": 3}, headers=headers)).json()
    assert len(items) == 3 and items[0]["question"] == "Does Tazocin need AMS approval?"
    # regression: a negative or zero limit was passed to SQL and returned a 500.
    for limit in (-1, 0):
        r = await client.get(f"{API}/query/history", params={"limit": limit}, headers=headers)
        assert r.status_code == 200 and len(r.json()) == 1
    other = (await client.get(f"{API}/query/history", headers=await login(client, ADMIN))).json()
    assert all(i["question"] != "Does Tazocin need AMS approval?" for i in other)


# --- sources & contacts -----------------------------------------------------------------------------


async def test_sources_open_cited_clause_and_file(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    citation = (await ask(client, HEPARIN_Q))["citations"][0]
    clinician = await login(client, CLINICIAN)
    source = (await client.get(f"{API}/sources/{citation['chunk_id']}", headers=clinician)).json()
    assert source["chunk_id"] == citation["chunk_id"] and source["is_current"]
    assert any(item["chunk_id"] == citation["chunk_id"] for item in source["outline"])

    file = await client.get(f"{API}/sources/{citation['version_id']}/file", headers=clinician)
    assert file.status_code == 200 and file.content

    assert (await client.get(f"{API}/sources/{uuid.uuid4()}", headers=clinician)).status_code == 404
    assert (await client.get(f"{API}/sources/{uuid.uuid4()}/file", headers=clinician)).status_code == 404
    assert (await client.get(f"{API}/sources/{citation['chunk_id']}")).status_code == 401


async def test_drafts_are_invisible_to_clinicians(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    draft_chunk = await scalar(
        "SELECT c.id FROM chunks c JOIN document_versions v ON v.id = c.version_id "
        "JOIN documents d ON d.id = v.document_id WHERE d.doc_code = 'C-2026-14' LIMIT 1"
    )
    clinician = await login(client, CLINICIAN)
    assert (await client.get(f"{API}/sources/{draft_chunk}", headers=clinician)).status_code == 404
    author = await login(client, AUTHOR)
    assert (await client.get(f"{API}/sources/{draft_chunk}", headers=author)).status_code == 200


async def test_contacts_are_network_wide_plus_own_branch(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    contacts = (await client.get(f"{API}/contacts", headers=await login(client, CLINICIAN))).json()
    labels = {c["role_label"] for c in contacts}
    assert "Duty senior doctor (network on-call)" in labels and "Duty doctor — Central" in labels
    assert "Duty doctor — Riverside" not in labels


# --- documents --------------------------------------------------------------------------------------


async def test_document_list_detail_and_chunks(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    author = await login(client, AUTHOR)
    assert (await client.get(f"{API}/documents", headers=await login(client, CLINICIAN))).status_code == 403
    docs = (await client.get(f"{API}/documents", headers=author)).json()
    assert {"P-ICU-07", "C-2026-09", "DG-01"} <= {d["doc_code"] for d in docs}

    drafts = (await client.get(f"{API}/documents", params={"status": "draft"}, headers=author)).json()
    assert [d["doc_code"] for d in drafts] == ["C-2026-14"]
    circulars = (await client.get(f"{API}/documents", params={"doc_type": "circular"}, headers=author)).json()
    assert all(d["doc_type"] == "circular" for d in circulars)
    searched = (await client.get(f"{API}/documents", params={"q": "heparin"}, headers=author)).json()
    assert "P-ICU-07" in {d["doc_code"] for d in searched}
    overdue = (await client.get(f"{API}/documents", params={"review_overdue": True}, headers=author)).json()
    assert all(d["review_overdue"] for d in overdue)

    doc = next(d for d in docs if d["doc_code"] == "P-ICU-07")
    detail = (await client.get(f"{API}/documents/{doc['id']}", headers=author)).json()
    assert detail["current_version_id"] and detail["supersessions_in"]
    version = detail["versions"][0]
    chunks = (await client.get(f"{API}/documents/{doc['id']}/versions/{version['id']}/chunks", headers=author)).json()
    assert len(chunks) == version["chunk_count"] > 0
    assert (await client.get(f"{API}/documents/{uuid.uuid4()}", headers=author)).status_code == 404
    wrong_pair = f"{API}/documents/{uuid.uuid4()}/versions/{version['id']}/chunks"
    assert (await client.get(wrong_pair, headers=author)).status_code == 404


async def test_extract_metadata_reads_header_tables(client: httpx.AsyncClient) -> None:
    author = await login(client, AUTHOR)
    r = await client.post(
        f"{API}/documents/extract-metadata",
        files={"file": ("p.md", TEST_PROTOCOL, "text/markdown")},
        headers=author,
    )
    # regression: "| Version | 1 |" header tables were not recognised (nothing was pre-filled).
    assert r.status_code == 200
    assert r.json() | {"title": None} == {
        "doc_code": "P-TEST-01",
        "version_label": "1",
        "effective_from": "2026-09-01",
        "review_due": None,
        "title": None,
    }
    # regression: an unreadable file raised a 500 instead of a validation error.
    empty = await client.post(
        f"{API}/documents/extract-metadata", files={"file": ("e.md", b"", "text/markdown")}, headers=author
    )
    assert empty.status_code == 422
    wrong_type = await client.post(
        f"{API}/documents/extract-metadata",
        files={"file": ("x.exe", b"MZ", "application/octet-stream")},
        headers=author,
    )
    assert wrong_type.status_code == 422
    clinician = await login(client, CLINICIAN)
    files = {"file": ("p.md", TEST_PROTOCOL, "text/markdown")}
    assert (await client.post(f"{API}/documents/extract-metadata", files=files, headers=clinician)).status_code == 403


async def upload_test_protocol(
    client: httpx.AsyncClient, content: bytes = TEST_PROTOCOL, **fields: str
) -> httpx.Response:
    form = {
        "doc_code": "P-TEST-01",
        "title": "Test Protocol",
        "doc_type": "protocol",
        "version_label": "1",
        "effective_from": "2026-09-01",
        "department_code": "ED",
        **fields,
    }
    return await client.post(
        f"{API}/documents",
        data=form,
        files={"file": ("P-TEST-01.md", content, "text/markdown")},
        headers=await login(client, AUTHOR),
    )


async def test_upload_validation(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    bad = await upload_test_protocol(client, doc_code="not a code", version_label="v 1!")
    assert bad.status_code == 422 and len(bad.json()["error"]["details"]) == 2
    empty = await upload_test_protocol(client, content=b"")
    assert empty.status_code == 422
    # The exact bytes of an already stored version are refused, whatever code they are uploaded under.
    author = await login(client, AUTHOR)
    stored = (await client.get(f"{API}/documents", params={"q": "P-ICU-07"}, headers=author)).json()[0]
    stored_bytes = (await client.get(f"{API}/sources/{stored['versions'][0]['id']}/file", headers=author)).content
    duplicate = await upload_test_protocol(client, content=stored_bytes, doc_code="P-TEST-02")
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "duplicate_file"


async def test_version_lifecycle_upload_approve_retire(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    r = await upload_test_protocol(client)
    assert r.status_code == 201, r.text
    created = r.json()
    await jobs.drain_inline()
    base = f"{API}/documents/{created['document_id']}/versions/{created['version_id']}"
    author, approver = await login(client, AUTHOR), await login(client, APPROVER)

    again = await upload_test_protocol(client, content=TEST_PROTOCOL + b"\nChanged.\n")
    assert again.status_code == 409 and again.json()["error"]["code"] == "duplicate_version"

    ack = await client.post(f"{base}/acknowledge-ocr", headers=author)
    assert ack.status_code == 200 and ack.json()["message"] == "No OCR warnings need acknowledgement"

    # regression: re-processing a version that is still being processed started a second, racing job.
    await execute(
        "UPDATE document_versions SET ingest_status = 'processing', updated_at = now() WHERE id = :id",
        id=created["version_id"],
    )
    busy = await client.post(f"{base}/reingest", headers=author)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "ingest_in_progress"
    # A job stuck for longer than the worker timeout is treated as dead and may be restarted.
    await execute(
        "UPDATE document_versions SET updated_at = now() - interval '1 hour' WHERE id = :id", id=created["version_id"]
    )
    assert (await client.post(f"{base}/reingest", headers=author)).status_code == 200
    await jobs.drain_inline()

    assert (await client.post(f"{base}/approve", headers=author)).status_code == 403
    approved = await client.post(f"{base}/approve", json={"confirm_suggested_supersessions": False}, headers=approver)
    assert approved.status_code == 200, approved.text
    await jobs.drain_inline()
    assert (await client.post(f"{base}/approve", headers=approver)).status_code == 409
    assert (await client.post(f"{base}/reingest", headers=author)).status_code == 409  # only drafts

    retired = await client.post(f"{base}/retire", headers=approver)
    assert retired.status_code == 200
    assert (await client.post(f"{base}/retire", headers=approver)).json()["message"] == "Already retired"
    assert (await client.post(f"{base}/retire", headers=author)).status_code == 403


# --- supersessions ----------------------------------------------------------------------------------


async def test_supersession_create_confirm_edit_delete(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    author, approver = await login(client, AUTHOR), await login(client, APPROVER)
    links = (await client.get(f"{API}/supersessions", headers=author)).json()
    assert {(link["source_doc_code"], link["target_doc_code"]) for link in links} >= {("C-2026-09", "P-ICU-07")}
    pending = (await client.get(f"{API}/supersessions", params={"confirmed": False}, headers=author)).json()
    assert pending and not any(link["confirmed"] for link in pending)

    docs = {d["doc_code"]: d for d in (await client.get(f"{API}/documents", headers=author)).json()}
    body = {
        "source_version_id": docs["DG-02"]["current_version_id"],
        "target_document_id": docs["P-HAEM-02"]["id"],
        "target_section_path": "9.9",
        "note": "test link",
    }
    assert (await client.post(f"{API}/supersessions", json=body, headers=author)).status_code == 403
    created = await client.post(f"{API}/supersessions", json=body, headers=approver)
    assert created.status_code == 201 and created.json()["confirmed"] is False
    link_id = created.json()["id"]

    self_link = body | {"target_document_id": docs["DG-02"]["id"]}
    assert (await client.post(f"{API}/supersessions", json=self_link, headers=approver)).status_code == 422

    patched = await client.patch(f"{API}/supersessions/{link_id}", json={"confirmed": True}, headers=approver)
    assert patched.status_code == 200 and patched.json()["confirmed"] is True
    assert (await client.patch(f"{API}/supersessions/{link_id}", json={}, headers=author)).status_code == 403

    assert (await client.delete(f"{API}/supersessions/{link_id}", headers=approver)).status_code == 200
    assert (await client.delete(f"{API}/supersessions/{link_id}", headers=approver)).status_code == 404


# --- feedback ---------------------------------------------------------------------------------------


async def test_feedback_create_route_and_resolve(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    answer = await ask(client, HEPARIN_Q)
    clinician = await login(client, CLINICIAN)
    sent = await client.post(
        f"{API}/feedback", json={"query_id": answer["query_id"], "kind": "outdated", "comment": "t"}, headers=clinician
    )
    assert sent.status_code == 201 and sent.json()["routed_to"]
    feedback_id = sent.json()["id"]

    other = await login(client, "arjun.iyer@dhn.example")
    body = {"query_id": answer["query_id"], "kind": "wrong"}
    assert (await client.post(f"{API}/feedback", json=body, headers=other)).status_code == 403
    unknown = {"query_id": str(uuid.uuid4()), "kind": "wrong"}
    assert (await client.post(f"{API}/feedback", json=unknown, headers=clinician)).status_code == 404

    assert (await client.get(f"{API}/feedback/inbox", headers=clinician)).status_code == 403
    admin_inbox = (await client.get(f"{API}/feedback/inbox", headers=await login(client, ADMIN))).json()
    assert feedback_id in {f["id"] for f in admin_inbox}

    routed_to = await scalar(
        "SELECT u.email FROM feedback f JOIN users u ON u.id = f.routed_to_user_id WHERE f.id = :id", id=feedback_id
    )
    outsider = PHARMACY_AUTHOR if routed_to != PHARMACY_AUTHOR else AUTHOR
    patch = {"status": "resolved", "resolution_note": "done"}
    assert (
        await client.patch(f"{API}/feedback/{feedback_id}", json=patch, headers=await login(client, outsider))
    ).status_code == 403
    owner = await login(client, routed_to)
    assert feedback_id in {f["id"] for f in (await client.get(f"{API}/feedback/inbox", headers=owner)).json()}
    resolved = await client.patch(f"{API}/feedback/{feedback_id}", json=patch, headers=owner)
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert (await client.patch(f"{API}/feedback/{uuid.uuid4()}", json=patch, headers=owner)).status_code == 404


# --- conflicts & admin ------------------------------------------------------------------------------


async def test_conflicts_resolve_and_reopen(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    await ask(client, "When should aPTT be repeated after a heparin rate change?")  # detects the aPTT conflict
    author = await login(client, AUTHOR)
    assert (await client.get(f"{API}/conflicts", headers=await login(client, CLINICIAN))).status_code == 403
    conflicts = (await client.get(f"{API}/conflicts", params={"status": "open"}, headers=author)).json()
    assert conflicts, "the aPTT recheck conflict should be open"
    conflict_id = conflicts[0]["id"]

    resolved = await client.patch(
        f"{API}/conflicts/{conflict_id}", json={"status": "resolved", "resolution_note": "fixed"}, headers=author
    )
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert await scalar("SELECT resolved_at IS NOT NULL FROM conflicts WHERE id = :id", id=conflict_id)

    # regression: re-opening kept the old resolver and resolution time.
    reopened = await client.patch(f"{API}/conflicts/{conflict_id}", json={"status": "open"}, headers=author)
    assert reopened.status_code == 200
    assert await scalar(
        "SELECT resolved_by IS NULL AND resolved_at IS NULL FROM conflicts WHERE id = :id", id=conflict_id
    )
    missing = await client.patch(f"{API}/conflicts/{uuid.uuid4()}", json={"status": "open"}, headers=author)
    assert missing.status_code == 404


async def test_admin_stats_audit_and_reference_data(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    await ask(client, HEPARIN_Q)
    admin, author = await login(client, ADMIN), await login(client, AUTHOR)

    stats = await client.get(f"{API}/admin/stats", params={"days": 7}, headers=admin)
    assert stats.status_code == 200 and stats.json()["total_questions"] > 0
    assert (await client.get(f"{API}/admin/stats", headers=author)).status_code == 403

    events = (await client.get(f"{API}/admin/audit", params={"action": "query", "limit": 5}, headers=admin)).json()
    assert 0 < len(events) <= 5 and all(e["action"].startswith("query") for e in events)
    csv = await client.get(f"{API}/admin/audit", params={"format": "csv", "limit": 5}, headers=admin)
    assert (
        csv.headers["content-type"].startswith("text/csv") and "lumina-audit.csv" in csv.headers["content-disposition"]
    )
    assert csv.text.splitlines()[0].startswith("seq,created_at,actor,action")
    assert (await client.get(f"{API}/admin/audit", headers=author)).status_code == 403

    verify = (await client.get(f"{API}/admin/audit/verify", headers=admin)).json()
    assert verify["ok"] and verify["events_checked"] > 0

    reference = (await client.get(f"{API}/admin/reference-data", headers=author)).json()
    assert {b["code"] for b in reference["branches"]} == {"CEN", "RIV", "HIL"} and "circular" in reference["doc_types"]
    assert (await client.get(f"{API}/admin/reference-data", headers=await login(client, CLINICIAN))).status_code == 403


async def test_admin_overview_shows_ai_trace_users_and_records(
    client: httpx.AsyncClient, corpus: dict[str, Any]
) -> None:
    await ask(client, "Does Tazocin need AMS approval?")
    await ask(client, "What heparin bolus should I give Mr Ramesh Kumar, 72 kg?")
    admin = await login(client, ADMIN)
    r = await client.get(f"{API}/admin/overview", params={"days": 30}, headers=admin)
    assert r.status_code == 200, r.text
    o = r.json()

    ai = o["ai"]
    assert ai["config"]["llm_provider"] == "none" and set(ai["config"]["prompt_versions"]) == {
        "classifier",
        "generator",
        "verifier",
    }
    assert ai["questions"] >= 2 and ai["claims_supported"] <= ai["claims_checked"]
    refused, answered = ai["recent"][0], ai["recent"][1]
    assert refused["route"] == "high_risk" and refused["route_source"] == "rules" and refused["route_reason"]
    assert "Ramesh" not in refused["question"] and refused["pii_redacted"]
    assert answered["generation_mode"] == "extractive" and answered["cited"] and answered["timings_ms"]["total"] > 0
    assert "Tazocin = piperacillin-tazobactam" in answered["expansions"]

    clinician = next(u for u in o["users"] if u["email"] == CLINICIAN)
    assert clinician["questions"] >= 2 and clinician["refused_high_risk"] >= 1
    assert len(o["users"]) == 9
    assert {d["doc_code"] for d in o["documents"]} >= {"P-ICU-07", "C-2026-14"}
    assert any(a["target"] == "P-ICU-07 §4.2" and a["confirmed"] for a in o["amendments"])
    assert isinstance(o["conflicts"], list) and isinstance(o["feedback"], list)

    for email in (APPROVER, AUTHOR, CLINICIAN):
        assert (await client.get(f"{API}/admin/overview", headers=await login(client, email))).status_code == 403
