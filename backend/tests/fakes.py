"""Test doubles."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.services.llm.base import LLMError

Handler = dict[str, Any] | Callable[[str, str], dict[str, Any]] | Exception


class ScriptedLLM:
    """Fake LLMProvider: returns scripted JSON per task and records every call it receives."""

    name = "fake"
    model_id = "fake-llm-1"

    def __init__(
        self,
        *,
        classify: Handler | None = None,
        generate: Handler | None = None,
        verify: Handler | None = None,
        conflict: Handler | None = None,
    ) -> None:
        self.handlers: dict[str, Handler | None] = {
            "classify": classify
            if classify is not None
            else {"route": "answer", "clarifying_question": "", "reason": "lookup"},
            "generate": generate,
            "verify": verify if verify is not None else {"supported": True, "score": 0.95, "issue": ""},
            "conflict": conflict
            if conflict is not None
            else {"contradicts": False, "confidence": 0.0, "description": ""},
        }
        self.calls: list[dict[str, str]] = []

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], task: str, max_tokens: int = 1024
    ) -> dict[str, Any]:
        self.calls.append({"task": task, "system": system, "user": user})
        handler = self.handlers.get(task)
        if task == "verify" and "verdicts" in system and handler is not None and not isinstance(handler, Exception):
            # Batched verification: apply the per-claim script to each numbered claim.
            verdicts = []
            for match in re.finditer(r"^(\d+)\. \(cites [^)]*\) (.*)$", user, re.MULTILINE):
                claim_prompt = f"Claim:\n{match.group(2)}"
                verdict = handler(system, claim_prompt) if callable(handler) else dict(handler)
                verdicts.append({"claim": int(match.group(1)), **verdict})
            return {"verdicts": verdicts}
        if handler is None:
            raise LLMError(f"no scripted response for {task}")
        if isinstance(handler, Exception):
            raise handler
        if callable(handler):
            return handler(system, user)
        return dict(handler)

    async def health(self) -> tuple[bool, str]:
        return True, "fake"

    def tasks(self) -> list[str]:
        return [c["task"] for c in self.calls]


def passage_markers(user_prompt: str) -> dict[str, str]:
    """{"S1": "<doc_code> §<path>", ...} parsed from a generator prompt."""
    return {
        m.group(1): f"{m.group(2)} §{m.group(3)}"
        for m in re.finditer(r"\[(S\d+)\] (\S+) \".*?\" v\S+ §(\S+),", user_prompt)
    }
