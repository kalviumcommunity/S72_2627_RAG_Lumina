"""Integration fixtures: a freshly migrated test database per module, the API over ASGI, and helpers.

Needs PostgreSQL with pgvector at TEST_DATABASE_URL (see tests/conftest.py).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.api.deps import rate_limiter
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services import jobs
from app.services.registry import Services, build_services, load_corpus_vocabulary, set_services
from tests.conftest import SAMPLE_CORPUS, TEST_DATABASE_URL


async def _reset_schema() -> None:
    from scripts.reset_db import reset

    await dispose_engine()
    await asyncio.to_thread(reset, TEST_DATABASE_URL, wipe_storage=False)
    init_engine(TEST_DATABASE_URL)


@pytest_asyncio.fixture(scope="module")
async def services() -> AsyncIterator[Services]:
    """Fresh schema + seed data; deterministic models (hash embeddings, lexical re-ranker, no LLM)."""
    try:
        await _reset_schema()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL test database unavailable: {type(exc).__name__}: {exc}")
    from scripts.seed import seed

    svc = build_services()
    set_services(svc)
    jobs.reset()
    rate_limiter.reset()
    await seed()
    yield svc
    set_services(None)
    await dispose_engine()


@pytest_asyncio.fixture(scope="module")
async def corpus(services: Services) -> dict[str, Any]:
    """The full synthetic sample corpus, ingested through the real pipeline (incl. OCR)."""
    from scripts.ingest_sample import load_corpus

    summary = await load_corpus(SAMPLE_CORPUS, detect_conflicts=True, verbose=False)
    assert not summary["failed"], summary["failed"]
    async with get_sessionmaker()() as session:
        await load_corpus_vocabulary(session)
    return summary


@pytest_asyncio.fixture(scope="module")
async def client(services: Services) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/dev-login", json={"email": email})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def scalar(sql: str, **params: Any) -> Any:
    async with get_sessionmaker()() as session:
        return (await session.execute(text(sql), params)).scalar()


CLINICIAN = "kavya.rao@dhn.example"  # Central
RIVERSIDE_CLINICIAN = "arjun.iyer@dhn.example"
AUTHOR = "meera.nair@dhn.example"  # owns P-ICU-07 and C-2026-09
PHARMACY_AUTHOR = "rahul.verma@dhn.example"
APPROVER = "sana.qureshi@dhn.example"
ADMIN = "nikhil.desai@dhn.example"
