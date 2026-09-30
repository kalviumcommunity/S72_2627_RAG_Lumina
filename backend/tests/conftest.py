"""Shared test configuration.

Environment is pinned BEFORE the app is imported: deterministic hash embeddings, lexical
re-ranker, no LLM (tests inject a scripted fake where needed), inline background jobs and a
dedicated test database (TEST_DATABASE_URL, default: the local native Postgres on port 5433).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="protocite-tests-"))
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://protocite:protocite@127.0.0.1:5433/protocite_test"
)
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "REDIS_URL": "redis://127.0.0.1:1/0",  # unreachable on purpose: inline jobs, local rate limiter
        "STORAGE_DIR": str(_TMP / "storage"),
        "INGEST_INLINE": "true",
        "LLM_PROVIDER": "none",
        "EMBEDDING_PROVIDER": "hash",
        "RERANKER_PROVIDER": "lexical",
        "WARMUP_MODELS": "false",
        "DEV_AUTH": "true",
        "SECRET_KEY": "test-secret-key-for-protocite-tests-only",
        "TODAY_OVERRIDE": "2026-09-30",
        "QUERY_RATE_LIMIT_PER_MINUTE": "1000",
        "LOG_JSON": "true",
        "OCR_LANGUAGES": "eng",
    }
)

import pytest  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CORPUS = Path(__file__).resolve().parents[2] / "sample_corpus"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "/integration/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES
