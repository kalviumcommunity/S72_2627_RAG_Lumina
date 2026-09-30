"""LLM resilience: time budgets, Gemini model fallback chain, glossary context."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.core.config import Settings
from app.services.generation.generator import build_user_prompt
from app.services.llm.base import LLMError
from app.services.llm.budget import BudgetedLLM
from app.services.llm.gemini_provider import GeminiProvider


class SlowLLM:
    name = "slow"
    model_id = "slow-1"

    async def complete_json(self, **_: Any) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {}

    async def health(self) -> tuple[bool, str]:
        return True, "ok"


async def test_stage_exceeding_its_budget_raises_llm_error_quickly() -> None:
    llm = BudgetedLLM(SlowLLM(), {"generate": 0.05})
    with pytest.raises(LLMError, match="budget"):
        await llm.complete_json(system="s", user="u", schema={}, task="generate")


def _ok_response() -> SimpleNamespace:
    return SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP")], text='{"answer": "ok"}')


def _provider(calls: list[str], failing: dict[str, int]) -> GeminiProvider:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="test-key-not-real",
        gemini_model="model-a,model-b",
        gemini_fast_model="model-fast",
        gemini_thinking_level="",
    )
    provider = GeminiProvider(settings)

    async def generate_content(*, model: str, contents: str, config: Any) -> SimpleNamespace:
        calls.append(model)
        if model in failing:
            code = failing[model]
            raise errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})
        return _ok_response()

    provider._client.aio.models.generate_content = generate_content  # type: ignore[union-attr]
    return provider


async def test_rate_limited_model_falls_through_to_the_next_one_and_rests() -> None:
    calls: list[str] = []
    provider = _provider(calls, {"model-a": 429})
    assert await provider.complete_json(system="s", user="u", schema={}, task="generate") == {"answer": "ok"}
    assert calls == ["model-a", "model-b"]
    calls.clear()
    await provider.complete_json(system="s", user="u", schema={}, task="generate")
    assert calls == ["model-b"]  # model-a is resting after its 429


async def test_fast_tasks_use_the_fast_model_first() -> None:
    calls: list[str] = []
    provider = _provider(calls, {})
    await provider.complete_json(system="s", user="u", schema={}, task="verify")
    assert calls == ["model-fast"]


async def test_all_models_unavailable_raises_llm_error() -> None:
    calls: list[str] = []
    provider = _provider(calls, {"model-a": 429, "model-b": 503, "model-fast": 429})
    with pytest.raises(LLMError):
        await provider.complete_json(system="s", user="u", schema={}, task="generate")


async def test_bad_request_is_not_retried_on_other_models() -> None:
    calls: list[str] = []
    provider = _provider(calls, {"model-a": 400})
    with pytest.raises(LLMError, match="400"):
        await provider.complete_json(system="s", user="u", schema={}, task="generate")
    assert calls == ["model-a"]


def test_glossary_from_the_abbreviation_list_reaches_the_generator() -> None:
    prompt = build_user_prompt("Does Tazocin need AMS approval?", [], [], [("Tazocin", "piperacillin-tazobactam")])
    assert "- Tazocin = piperacillin-tazobactam" in prompt
    assert "approved abbreviation list" in prompt
