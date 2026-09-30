"""Ollama provider (local inference, keeps all data on the host)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import Settings
from app.services.llm.base import LLMError, LLMTask, parse_json_object


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.ollama_model
        self._base = settings.ollama_base_url.rstrip("/")
        self._num_ctx = settings.ollama_num_ctx
        self._timeout = settings.llm_timeout_seconds
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        task: LLMTask,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model_id,
            "stream": False,
            "format": schema,
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_ctx": self._num_ctx, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(f"{self._base}/api/chat", json=payload)
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"Ollama returned HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"Could not reach Ollama: {type(exc).__name__}") from exc
        content = (response.json().get("message") or {}).get("content", "")
        return parse_json_object(content)

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._base}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return False, f"unreachable: {type(exc).__name__}"
        names = {m.get("name", "") for m in response.json().get("models", [])}
        if not any(n == self.model_id or n.startswith(self.model_id + ":") for n in names):
            return False, f"model {self.model_id} not pulled"
        return True, f"{self.model_id} available"
