"""Anthropic Claude provider (structured outputs via output_config.format)."""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic

from app.core.config import Settings
from app.services.llm.base import LLMError, LLMNotConfiguredError, LLMTask, parse_json_object

# Short judgements run at the lowest effort; answer generation uses the configured effort.
_TASK_EFFORT: dict[str, str] = {"classify": "low", "verify": "low", "conflict": "low"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.anthropic_model
        self._effort = settings.anthropic_effort
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        self._client: anthropic.AsyncAnthropic | None = None
        if settings.anthropic_api_key:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=2,
            )

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        task: LLMTask,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        if self._client is None:
            raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set")
        async with self._semaphore:
            try:
                params: dict[str, Any] = {
                    "model": self.model_id,
                    "max_tokens": max_tokens + 4096,  # headroom for adaptive thinking
                    # Stable system prompt first so repeated calls hit the prompt cache.
                    "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    "messages": [{"role": "user", "content": user}],
                    "output_config": {
                        "effort": _TASK_EFFORT.get(task, self._effort),
                        "format": {"type": "json_schema", "schema": schema},
                    },
                    # If a safety classifier declines, the API retries on a suitable fallback model.
                    "betas": ["server-side-fallback-2026-07-01"],
                    "fallbacks": "default",
                }
                response = await self._client.beta.messages.create(**params)
            except anthropic.AuthenticationError as exc:
                raise LLMNotConfiguredError("Anthropic rejected the API key") from exc
            except anthropic.RateLimitError as exc:
                raise LLMError("Anthropic rate limit reached") from exc
            except anthropic.APIStatusError as exc:
                raise LLMError(f"Anthropic API error ({exc.status_code})") from exc
            except anthropic.APIConnectionError as exc:
                raise LLMError("Could not reach the Anthropic API") from exc
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude response was truncated")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return parse_json_object(text)

    async def health(self) -> tuple[bool, str]:
        if self._client is None:
            return False, "ANTHROPIC_API_KEY is not set"
        try:
            model = await self._client.models.retrieve(self.model_id)
        except anthropic.APIError as exc:
            return False, f"model lookup failed: {type(exc).__name__}"
        return True, f"{model.id} reachable"
