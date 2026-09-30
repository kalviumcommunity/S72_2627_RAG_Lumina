"""The frontend's typed client is generated from frontend/src/lib/openapi.json: keep it in sync."""

from __future__ import annotations

import pytest

from scripts.export_openapi import TARGET, current_schema, render


def test_committed_openapi_schema_matches_the_api() -> None:
    if not TARGET.exists():
        pytest.skip("frontend not present")
    assert TARGET.read_text(encoding="utf-8") == render(current_schema()), (
        "API schema changed: run `python -m scripts.export_openapi` in backend/ and `pnpm gen:types` in frontend/"
    )


def test_core_contract_fields_exist() -> None:
    schemas = current_schema()["components"]["schemas"]
    response = schemas["QueryResponse"]["properties"]
    for field in (
        "query_id",
        "route",
        "outcome",
        "answer",
        "citations",
        "quick_values",
        "conflicts",
        "escalation",
        "latency_ms",
        "disclaimer",
    ):
        assert field in response
    citation = schemas["CitationOut"]["properties"]
    for field in (
        "marker",
        "chunk_id",
        "doc_code",
        "title",
        "version",
        "section_path",
        "page",
        "effective_from",
        "supersedes",
        "snippet",
        "supported",
    ):
        assert field in citation
