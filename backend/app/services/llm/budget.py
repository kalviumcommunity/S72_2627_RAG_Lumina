"""Per-task time budgets around any LLM provider.

A hosted LLM can be slow or rate-limited at the worst moment. Each pipeline stage has a safe
deterministic fallback (rules classifier, verbatim extractive answer, lexical verifier), so a
stage that exceeds its budget raises LLMError and the pipeline moves on instead of making an
on-call clinician wait.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.services.llm.base import LLMError, LLMProvider, LLMTask


@dataclass
class TaskUsage:
    """LLM calls for one pipeline stage since the process started (shown on the admin page)."""

    calls: int = 0
    failures: int = 0
    timeouts: int = 0
    total_ms: float = 0.0

    @property
    def avg_ms(self) -> float | None:
        return round(self.total_ms / self.calls, 1) if self.calls else None


class BudgetedLLM:
    def __init__(self, inner: LLMProvider, budgets: dict[str, float]) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.budgets = budgets
        self.usage: dict[str, TaskUsage] = {}

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        task: LLMTask,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        budget = self.budgets.get(task)
        usage = self.usage.setdefault(task, TaskUsage())
        usage.calls += 1
        started = time.perf_counter()
        call = self.inner.complete_json(system=system, user=user, schema=schema, task=task, max_tokens=max_tokens)
        try:
            if not budget:
                return await call
            try:
                return await asyncio.wait_for(call, timeout=budget)
            except TimeoutError as exc:
                usage.timeouts += 1
                raise LLMError(f"{self.name} {task} exceeded its {budget:g}s budget") from exc
        except Exception:
            usage.failures += 1
            raise
        finally:
            usage.total_ms += (time.perf_counter() - started) * 1000

    async def health(self) -> tuple[bool, str]:
        return await self.inner.health()
