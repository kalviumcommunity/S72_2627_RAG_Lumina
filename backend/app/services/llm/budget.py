"""Per-task time budgets around any LLM provider.

A hosted LLM can be slow or rate-limited at the worst moment. Each pipeline stage has a safe
deterministic fallback (rules classifier, verbatim extractive answer, lexical verifier), so a
stage that exceeds its budget raises LLMError and the pipeline moves on instead of making an
on-call clinician wait.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.llm.base import LLMError, LLMProvider, LLMTask


class BudgetedLLM:
    def __init__(self, inner: LLMProvider, budgets: dict[str, float]) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.budgets = budgets

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
        call = self.inner.complete_json(system=system, user=user, schema=schema, task=task, max_tokens=max_tokens)
        if not budget:
            return await call
        try:
            return await asyncio.wait_for(call, timeout=budget)
        except TimeoutError as exc:
            raise LLMError(f"{self.name} {task} exceeded its {budget:g}s budget") from exc

    async def health(self) -> tuple[bool, str]:
        return await self.inner.health()
