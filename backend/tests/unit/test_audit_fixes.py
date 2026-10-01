"""Regression tests for bugs found in the codebase audit (no database needed)."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest

from app.services.generation.generator import extractive_answer
from app.services.ingestion.metadata import extract_metadata
from app.services.llm.base import LLMError
from app.services.llm.budget import BudgetedLLM
from app.services.safety.pii_redaction import PIIRedactor
from tests.unit.test_extractive import passage

HEADER = """# P-ICU-07 Heparin Infusion Protocol (Adult ICU)

> SYNTHETIC. This version has been superseded by version 3.

| Field | Value |
|---|---|
| Document code | P-ICU-07 |
| Version | 2 |
| Effective from | 2024-01-10 |
| Review due | 10 January 2026 |

## 1 Purpose

In partial modification of the heparin protocol (version 3), effective 1 September 2026, the table changes.
"""


def test_metadata_is_read_from_the_header_table_not_from_prose() -> None:
    meta = extract_metadata(HEADER)
    assert meta.doc_code == "P-ICU-07"
    assert meta.version_label == "2"  # not "3" from "superseded by version 3"
    assert meta.effective_from == date(2024, 1, 10)  # not the date mentioned in the body
    assert meta.review_due == date(2026, 1, 10)
    assert meta.title == "P-ICU-07 Heparin Infusion Protocol (Adult ICU)"


def test_metadata_accepts_plain_label_lines_and_circular_numbers() -> None:
    meta = extract_metadata("Circular number: C-2026-21\nVersion: v1.1\nEffective from - 2026-09-20\n")
    assert (meta.doc_code, meta.version_label, meta.effective_from) == ("C-2026-21", "1.1", date(2026, 9, 20))


class _Inner:
    name = "fake"
    model_id = "fake-1"

    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour

    async def complete_json(self, **_: Any) -> dict[str, Any]:
        if self.behaviour == "slow":
            await asyncio.sleep(1)
        if self.behaviour == "fail":
            raise LLMError("boom")
        return {"ok": True}

    async def health(self) -> tuple[bool, str]:
        return True, "fake"


async def _call(llm: BudgetedLLM, task: str) -> dict[str, Any]:
    return await llm.complete_json(system="s", user="u", schema={}, task=task)  # type: ignore[arg-type]


async def test_llm_usage_counts_calls_failures_and_timeouts() -> None:
    ok = BudgetedLLM(_Inner("ok"), {"classify": 1.0})
    assert await _call(ok, "classify") == {"ok": True}
    assert (ok.usage["classify"].calls, ok.usage["classify"].failures) == (1, 0)
    assert ok.usage["classify"].avg_ms is not None

    failing = BudgetedLLM(_Inner("fail"), {})
    with pytest.raises(LLMError):
        await _call(failing, "generate")
    assert (failing.usage["generate"].calls, failing.usage["generate"].failures) == (1, 1)

    slow = BudgetedLLM(_Inner("slow"), {"verify": 0.01})
    with pytest.raises(LLMError):
        await _call(slow, "verify")
    assert (slow.usage["verify"].failures, slow.usage["verify"].timeouts) == (1, 1)


def test_pii_status_reports_the_configured_engine_before_first_use() -> None:
    assert PIIRedactor("presidio").status == "presidio (loads on first question)"
    regex = PIIRedactor("regex")
    regex.redact("hello")
    assert regex.status == "regex"


def test_extractive_key_values_are_not_repeated() -> None:
    p = passage(
        "S1",
        "Repeat the aPTT 6 hours after starting the infusion and 6 hours after every rate change.",
        heading="Monitoring",
    )
    draft = extractive_answer("When should aPTT be repeated?", [p], [])
    values = [(q["value"], q["source"]) for q in draft.quick_values]
    assert values == [("6 hours", "S1")]
    assert draft.quick_values[0]["label"] == "Repeat the aPTT"


def test_production_refuses_the_demo_secret_and_demo_sign_in() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(app_env="prod", secret_key="change-me", dev_auth=False)
    with pytest.raises(ValidationError, match="DEV_AUTH"):
        Settings(app_env="prod", secret_key="x" * 40, dev_auth=True)
    assert Settings(app_env="prod", secret_key="x" * 40, dev_auth=False).is_prod
    assert Settings(app_env="dev", secret_key="change-me", dev_auth=True).dev_auth  # demos are unaffected
