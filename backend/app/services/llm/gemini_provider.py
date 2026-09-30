"""Google Gemini provider (google-genai SDK), with optional Vertex AI regional pinning."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from google import genai
from google.genai import errors, types

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.llm.base import (
    LLMError,
    LLMNotConfiguredError,
    LLMTask,
    parse_json_object,
    strip_schema_keywords,
)

_THINKING_LEVELS: dict[str, types.ThinkingLevel] = {
    "minimal": types.ThinkingLevel.MINIMAL,
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}
# Short yes/no judgements do not need the generator's reasoning budget.
_TASK_THINKING: dict[str, str] = {"classify": "minimal", "verify": "minimal", "conflict": "minimal"}
# Tasks that run on the fast model (GEMINI_FAST_MODEL) when one is configured.
_FAST_TASKS = frozenset({"classify", "verify", "conflict"})
log = get_logger(__name__)


def _models(value: str) -> list[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        # GEMINI_MODEL / GEMINI_FAST_MODEL may be comma-separated lists. Answer writing tries the
        # main models first; routing / verification (short judgements) try the fast models first.
        # Each chain ends with the other list, so any model with quota left can serve a request.
        main = _models(settings.gemini_model)
        fast = _models(settings.gemini_fast_model) or main
        self._chains: dict[str, list[str]] = {
            "main": list(dict.fromkeys(main + fast)),
            "fast": list(dict.fromkeys(fast + main)),
        }
        self.model_id = main[0]
        self.fast_model_id = fast[0]
        self._cooldown_until: dict[str, float] = {}  # model -> monotonic time it may be retried
        self._thinking = settings.gemini_thinking_level
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
        http_options = types.HttpOptions(
            timeout=int(settings.llm_timeout_seconds * 1000),
            # No blind retry/backoff: an overloaded or rate-limited model moves straight to the next
            # model in the chain (see complete_json), which is faster than waiting on the same one.
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        self._client: genai.Client | None = None
        if settings.gemini_use_vertex:
            if not settings.google_cloud_project:
                self._config_error = "GOOGLE_CLOUD_PROJECT is required when GEMINI_USE_VERTEX=true"
                return
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                http_options=http_options,
            )
        elif settings.gemini_api_key:
            self._client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
        else:
            self._config_error = "GEMINI_API_KEY is not set"
            return
        self._config_error = ""

    def _thinking_config(self, task: LLMTask) -> types.ThinkingConfig | None:
        level = _TASK_THINKING.get(task, self._thinking) if self._thinking else ""
        if not level:
            return None
        return types.ThinkingConfig(thinking_level=_THINKING_LEVELS[level])

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
            raise LLMNotConfiguredError(self._config_error)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=max_tokens + 2048,  # thinking tokens count against this budget
            response_mime_type="application/json",
            response_json_schema=strip_schema_keywords(schema, frozenset({"additionalProperties"})),
            thinking_config=self._thinking_config(task),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        chain = self._chains["fast" if task in _FAST_TASKS else "main"]
        now = time.monotonic()
        ready = [m for m in chain if self._cooldown_until.get(m, 0.0) <= now] or chain[:1]
        last_error: LLMError | None = None
        async with self._semaphore:
            for model in ready:
                try:
                    response = await self._client.aio.models.generate_content(model=model, contents=user, config=config)
                    break
                except errors.APIError as exc:
                    if exc.code in (429, 503, 404):
                        # Quota / overload / unknown model: rest this model, try the next one.
                        rest = {429: 60.0, 503: 15.0, 404: 3600.0}[exc.code]
                        self._cooldown_until[model] = time.monotonic() + rest
                        log.warning("gemini_model_unavailable", model=model, status=exc.code, next_try_s=rest)
                        last_error = LLMError(f"Gemini {model} unavailable ({exc.code})")
                        continue
                    if isinstance(exc, errors.ClientError):
                        raise LLMError(f"Gemini rejected the request ({exc.code}: bad request)") from exc
                    raise LLMError(f"Gemini service error ({exc.code})") from exc
                except Exception as exc:  # network / timeout
                    raise LLMError(f"Gemini call failed: {type(exc).__name__}") from exc
            else:
                raise last_error or LLMError("No Gemini model available")
        candidate = response.candidates[0] if response.candidates else None
        finish = getattr(candidate, "finish_reason", None)
        if finish is not None and str(finish).upper().endswith(("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST")):
            raise LLMError(f"Gemini blocked the response ({finish})")
        if not response.text:
            raise LLMError(f"Gemini returned no text (finish_reason={finish})")
        return parse_json_object(response.text)

    async def health(self) -> tuple[bool, str]:
        if self._client is None:
            return False, self._config_error
        reachable: list[str] = []
        for name in self._chains["main"]:
            try:
                await self._client.aio.models.get(model=name)
            except Exception as exc:
                log.info("gemini_model_lookup_failed", model=name, error_type=type(exc).__name__)
                continue
            reachable.append(name)
        if not reachable:
            return False, "no configured Gemini model is reachable"
        resting = [m for m, t in self._cooldown_until.items() if t > time.monotonic()]
        detail = ", ".join(reachable) + (f" (rate-limited now: {', '.join(resting)})" if resting else "")
        return True, detail
