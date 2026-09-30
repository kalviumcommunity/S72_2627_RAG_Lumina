"""LLM provider protocol.

Every call returns a JSON object constrained by a schema. `task` lets a provider pick a cheaper
reasoning setting for short judgements (classify / verify) than for answer generation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

LLMTask = Literal["classify", "generate", "verify", "conflict"]


class LLMError(Exception):
    """Raised for any provider failure (network, auth, refusal, invalid JSON)."""


class LLMNotConfiguredError(LLMError):
    """The selected provider has no credentials / endpoint configured."""


class LLMProvider(Protocol):
    name: str
    model_id: str

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        task: LLMTask,
        max_tokens: int = 1024,
    ) -> dict[str, Any]: ...

    async def health(self) -> tuple[bool, str]: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text, tolerating code fences and leading prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model did not return a JSON object") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("Model returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise LLMError("Model returned JSON that is not an object")
    return value


def strip_schema_keywords(schema: Any, keywords: frozenset[str]) -> Any:
    """Recursively drop JSON-schema keywords a provider does not accept."""
    if isinstance(schema, dict):
        return {k: strip_schema_keywords(v, keywords) for k, v in schema.items() if k not in keywords}
    if isinstance(schema, list):
        return [strip_schema_keywords(v, keywords) for v in schema]
    return schema
