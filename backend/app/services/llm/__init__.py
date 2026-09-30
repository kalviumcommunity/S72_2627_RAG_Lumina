"""LLM provider factory."""

from __future__ import annotations

from app.core.config import Settings
from app.services.llm.base import LLMError, LLMNotConfiguredError, LLMProvider
from app.services.llm.budget import BudgetedLLM


def _raw_provider(settings: Settings) -> LLMProvider | None:
    if settings.llm_provider == "gemini":
        from app.services.llm.gemini_provider import GeminiProvider

        return GeminiProvider(settings)
    if settings.llm_provider == "anthropic":
        from app.services.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    if settings.llm_provider == "ollama":
        from app.services.llm.ollama_provider import OllamaProvider

        return OllamaProvider(settings)
    return None


def build_llm(settings: Settings) -> LLMProvider | None:
    """The configured provider wrapped in per-stage time budgets, or None (deterministic mode)."""
    provider = _raw_provider(settings)
    if provider is None:
        return None
    return BudgetedLLM(
        provider,
        {
            "classify": settings.llm_budget_classify_s,
            "generate": settings.llm_budget_generate_s,
            "verify": settings.llm_budget_verify_s,
            "conflict": settings.llm_budget_conflict_s,
        },
    )


__all__ = ["LLMError", "LLMNotConfiguredError", "LLMProvider", "build_llm"]
