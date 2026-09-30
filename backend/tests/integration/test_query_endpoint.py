"""/query end to end (M4 acceptance): unsupported or uncited text never reaches the client."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.api.deps import rate_limiter
from app.core.config import get_settings
from app.services.registry import Services
from tests.fakes import ScriptedLLM, passage_markers
from tests.integration.conftest import (
    AUTHOR,
    CLINICIAN,
    PHARMACY_AUTHOR,
    RIVERSIDE_CLINICIAN,
    login,
    scalar,
)

HEPARIN_Q = "What is the heparin infusion nomogram rate change for aPTT above 100?"
FAKE_CLAIM = "Give an extra 5000 units heparin bolus immediately"


def _marker_for(user_prompt: str, prefix: str) -> str | None:
    markers = passage_markers(user_prompt)
    return next((m for m, label in markers.items() if label.startswith(prefix)), None)


def heparin_generator(system: str, user: str) -> dict[str, Any]:
    circ = _marker_for(user, "C-2026-09 §2")
    if circ is None:
        return {"answer": "NOT_FOUND", "quick_values": []}
    return {
        "answer": (
            f"Stop the infusion for 1 hour, then restart at a rate reduced by 3 units/kg/h [{circ}]. "
            f"{FAKE_CLAIM} [{circ}]. Heparin is very safe."
        ),
        "quick_values": [
            {"label": "Hold", "value": "1 hour", "source": circ},
            {"label": "Bolus", "value": "5000 units", "source": circ},
        ],
    }


@pytest.fixture
def scripted(services: Services) -> Iterator[ScriptedLLM]:
    """Swap in a scripted LLM whose judge approves EVERYTHING (the worst case for the gate)."""
    llm = ScriptedLLM(generate=heparin_generator, verify={"supported": True, "score": 0.99, "issue": ""})
    previous = services.llm
    services.llm = llm
    yield llm
    services.llm = previous


async def ask(client: httpx.AsyncClient, email: str, question: str) -> dict[str, Any]:
    response = await client.post("/api/v1/query", json={"question": question}, headers=await login(client, email))
    assert response.status_code == 200, response.text
    return response.json()


async def test_injected_fake_claim_never_reaches_the_client(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    body = await ask(client, CLINICIAN, HEPARIN_Q)
    assert body["route"] == "answer" and body["outcome"] == "partial"
    assert "Stop the infusion for 1 hour" in body["answer"]
    assert "5000" not in body["answer"] and FAKE_CLAIM not in body["answer"]
    assert "very safe" not in body["answer"]  # uncited sentence removed
    assert [q["value"] for q in body["quick_values"]] == ["1 hour"]  # fabricated quick value dropped
    assert body["verification"]["supported"] < body["verification"]["claims"]


async def test_answer_cites_current_amendment_not_superseded_text(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    body = await ask(client, CLINICIAN, HEPARIN_Q)
    (citation,) = body["citations"]
    assert citation["doc_code"] == "C-2026-09" and citation["section_path"] == "2"
    assert citation["effective_from"] == "2026-09-01"
    assert citation["supersedes"] == {"doc_code": "P-ICU-07", "section_path": "4.2"}
    # The superseded nomogram (P-ICU-07 v3 §4.2) and the old v2 never reached the generator.
    labels = passage_markers(next(c["user"] for c in scripted.calls if c["task"] == "generate")).values()
    assert "P-ICU-07 §4.2" not in labels
    assert all(s["doc_code"] != "P-ICU-07" or s["version"] == "3" for s in body["sources"])


async def test_all_claims_unsupported_means_abstain(
    client: httpx.AsyncClient, corpus: dict[str, Any], services: Services
) -> None:
    llm = ScriptedLLM(
        generate=lambda s, u: {
            "answer": f"Give 7 g of magnesium [{_marker_for(u, 'C-2026-09') or 'S1'}].",
            "quick_values": [],
        },
        verify={"supported": False, "score": 0.1, "issue": "not in passage"},
    )
    previous, services.llm = services.llm, llm
    try:
        body = await ask(client, CLINICIAN, HEPARIN_Q)
    finally:
        services.llm = previous
    assert body["outcome"] == "abstained" and body["answer"] is None
    assert body["escalation"]["reason"] == "not_found" and body["escalation"]["contacts"]


async def test_generator_not_found_means_abstain(
    client: httpx.AsyncClient, corpus: dict[str, Any], services: Services
) -> None:
    previous, services.llm = services.llm, ScriptedLLM(generate={"answer": "NOT_FOUND", "quick_values": []})
    try:
        body = await ask(client, CLINICIAN, HEPARIN_Q)
    finally:
        services.llm = previous
    assert body["outcome"] == "abstained" and body["escalation"]["reason"] == "not_found"


async def test_sse_streams_route_sources_then_verified_answer(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    headers = await login(client, CLINICIAN)
    events: list[tuple[str, dict[str, Any]]] = []
    async with client.stream("POST", "/api/v1/query/stream", json={"question": HEPARIN_Q}, headers=headers) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        raw = (await r.aread()).decode()
    for block in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    assert [e for e, _ in events] == ["route", "sources", "answer", "done"]
    answer = events[2][1]["answer"]
    assert "Stop the infusion for 1 hour" in answer
    assert FAKE_CLAIM not in raw and "5000" not in raw  # never streamed, in any event
    # Source cards may quote approved documents verbatim, but the generated answer itself only
    # appears after verification.
    for name, data in events[:2]:
        assert answer not in json.dumps(data), f"answer text leaked in {name}"


async def test_sse_get_variant(client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM) -> None:
    headers = await login(client, CLINICIAN)
    r = await client.get("/api/v1/query/stream", params={"q": HEPARIN_Q}, headers=headers)
    assert r.status_code == 200 and "event: answer" in r.text


async def test_high_risk_question_is_refused_with_escalation(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    body = await ask(client, CLINICIAN, "What heparin bolus should I give Mr Ramesh Kumar who weighs 72 kg?")
    assert body["route"] == "high_risk" and body["outcome"] == "abstained" and body["answer"] is None
    assert body["escalation"]["reason"] == "high_risk"
    assert any("pharmacist" in c["role_label"].lower() for c in body["escalation"]["contacts"])
    assert "generate" not in scripted.tasks()


async def test_out_of_scope_and_not_found(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    out = await ask(client, CLINICIAN, "Who won the cricket match yesterday?")
    assert out["route"] == "out_of_scope" and out["escalation"]["reason"] == "out_of_scope"
    # (Tests use a lexical re-ranker; the real cross-encoder is exercised by the eval harness.)
    missing = await ask(client, CLINICIAN, "What are the car parking charges for visitors?")
    assert missing["outcome"] == "abstained" and missing["escalation"]["reason"] == "not_found"


async def test_branch_specific_document_serves_its_branch_only(
    client: httpx.AsyncClient, corpus: dict[str, Any]
) -> None:
    question = "Who do I call to activate the massive transfusion protocol at Riverside?"
    riverside = await ask(client, RIVERSIDE_CLINICIAN, question)
    assert riverside["citations"][0]["doc_code"] == "SOP-RIV-01"
    assert riverside["citations"][0]["branch_specific"] is True
    central = await ask(client, CLINICIAN, question)
    assert all(c["doc_code"] != "SOP-RIV-01" for c in central["citations"] + central["sources"])


async def test_conflict_is_surfaced_with_both_sources(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    body = await ask(client, CLINICIAN, "When should the aPTT be repeated after a heparin rate change?")
    assert body["conflicts"], body
    conflict = body["conflicts"][0]
    assert {conflict["a"]["doc_code"], conflict["b"]["doc_code"]} == {"P-ICU-07", "DG-02"}
    assert conflict["flagged_to_owner"] is True
    assert "6 hours" in body["answer"] and "4 hours" in body["answer"]


async def test_patient_identifiers_never_appear_in_logs_db_or_llm_prompts(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    secrets = ["Ramesh", "Kumar", "9876543210", "20231145"]
    question = "Mr Ramesh Kumar (UHID 20231145, son on 9876543210) — what is the nomogram step for aPTT above 100?"
    root = logging.getLogger()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)
    try:
        body = await ask(client, CLINICIAN, question)
    finally:
        root.removeHandler(handler)
    logs = stream.getvalue()
    assert "query_completed" in logs  # the log line exists…
    for secret in secrets:  # …but no identifier anywhere
        assert secret not in logs, f"{secret} leaked into logs"
        assert secret not in json.dumps(body)
        assert await scalar("SELECT count(*) FROM query_logs WHERE redacted_question LIKE :s", s=f"%{secret}%") == 0
        assert await scalar("SELECT count(*) FROM audit_events WHERE payload::text LIKE :s", s=f"%{secret}%") == 0
        assert all(secret not in call["user"] for call in scripted.calls)
    assert body["pii_redacted"] is True and "<PERSON>" in body["redacted_question"]


async def test_history_returns_redacted_questions(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    headers = await login(client, CLINICIAN)
    await client.post("/api/v1/query", json={"question": "Is Mrs Sunita Sharma due her heparin?"}, headers=headers)
    history = (await client.get("/api/v1/query/history", headers=headers)).json()
    assert history and all("Sunita" not in item["question"] for item in history)


async def test_feedback_is_routed_to_the_cited_documents_owner(
    client: httpx.AsyncClient, corpus: dict[str, Any], scripted: ScriptedLLM
) -> None:
    body = await ask(client, CLINICIAN, HEPARIN_Q)
    headers = await login(client, CLINICIAN)
    fb = await client.post(
        "/api/v1/feedback",
        json={
            "query_id": body["query_id"],
            "kind": "outdated",
            "comment": "Bedside folder still shows the old table",
        },
        headers=headers,
    )
    assert fb.status_code == 201, fb.text
    assert fb.json()["routed_to"] == "Dr Meera Nair"
    owner_inbox = (await client.get("/api/v1/feedback/inbox", headers=await login(client, AUTHOR))).json()
    assert any(item["id"] == fb.json()["id"] for item in owner_inbox)
    other_inbox = (await client.get("/api/v1/feedback/inbox", headers=await login(client, PHARMACY_AUTHOR))).json()
    assert all(item["id"] != fb.json()["id"] for item in other_inbox)
    # Clinicians cannot flag someone else's answer.
    other = await client.post(
        "/api/v1/feedback",
        json={"query_id": body["query_id"], "kind": "wrong"},
        headers=await login(client, RIVERSIDE_CLINICIAN),
    )
    assert other.status_code == 403


async def test_auth_and_rbac(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    assert (await client.post("/api/v1/query", json={"question": HEPARIN_Q})).status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert (await client.post("/api/v1/query", json={"question": HEPARIN_Q}, headers=bad)).status_code == 401
    clinician = await login(client, CLINICIAN)
    assert (await client.get("/api/v1/documents", headers=clinician)).status_code == 403
    assert (await client.get("/api/v1/admin/stats", headers=clinician)).status_code == 403
    files = {"file": ("x.md", b"# x\n\n## 1 A\n\ntext", "text/markdown")}
    form = {
        "doc_code": "P-X-01",
        "title": "X",
        "doc_type": "protocol",
        "version_label": "1",
        "effective_from": "2026-01-01",
    }
    assert (await client.post("/api/v1/documents", data=form, files=files, headers=clinician)).status_code == 403


async def test_clinicians_cannot_open_draft_sources(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    draft_chunk = await scalar("""
        SELECT c.id FROM chunks c JOIN document_versions v ON v.id = c.version_id
        JOIN documents d ON d.id = v.document_id WHERE d.doc_code = 'C-2026-14' LIMIT 1""")
    assert (
        await client.get(f"/api/v1/sources/{draft_chunk}", headers=await login(client, CLINICIAN))
    ).status_code == 404
    assert (await client.get(f"/api/v1/sources/{draft_chunk}", headers=await login(client, AUTHOR))).status_code == 200


async def test_source_view_of_superseded_clause_names_the_amendment(
    client: httpx.AsyncClient, corpus: dict[str, Any]
) -> None:
    old_clause = await scalar("""
        SELECT c.id FROM chunks c JOIN document_versions v ON v.id = c.version_id
        JOIN documents d ON d.id = v.document_id
        WHERE d.doc_code = 'P-ICU-07' AND v.version_label = '3' AND c.section_path = '4.2'""")
    source = (await client.get(f"/api/v1/sources/{old_clause}", headers=await login(client, CLINICIAN))).json()
    assert source["superseded_by"][0]["doc_code"] == "C-2026-09"
    assert list(dict.fromkeys(o["section_path"] for o in source["outline"]))[:4] == ["0", "1", "2", "3-4"]
    file = await client.get(
        source["file_url"].removeprefix("http://testserver"), headers=await login(client, CLINICIAN)
    )
    assert file.status_code == 200 and b"P-ICU-07" in file.content


async def test_rate_limit(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    settings = get_settings()
    previous = settings.query_rate_limit_per_minute
    settings.query_rate_limit_per_minute = 2
    rate_limiter.reset()
    try:
        headers = await login(client, CLINICIAN)
        codes = [
            (await client.post("/api/v1/query", json={"question": "hello"}, headers=headers)).status_code
            for _ in range(3)
        ]
    finally:
        settings.query_rate_limit_per_minute = previous
        rate_limiter.reset()
    assert codes == [200, 200, 429]


async def test_validation_rejects_empty_and_huge_questions(client: httpx.AsyncClient, corpus: dict[str, Any]) -> None:
    headers = await login(client, CLINICIAN)
    assert (await client.post("/api/v1/query", json={"question": ""}, headers=headers)).status_code == 422
    assert (await client.post("/api/v1/query", json={"question": "x" * 5000}, headers=headers)).status_code == 422


async def test_security_headers(client: httpx.AsyncClient, services: Services) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]
