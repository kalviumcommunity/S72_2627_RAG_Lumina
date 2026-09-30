# ADR 0004: Pluggable LLM Provider Architecture with Strict Local Fallback

## Status
Accepted

## Context
Hospital IT environments operate under varying governance constraints. Some healthcare networks allow HIPAA/DPDP-compliant cloud AI APIs (Google Gemini via Vertex AI in India region or Anthropic Claude with signed DPA), while air-gapped facilities mandate 100% on-premises data residency. Additionally, external API outages or rate limits must never compromise hospital lookups.

## Decision
We define an abstract `LLMProvider` protocol with multiple interchangeable implementations:
1. `gemini` (Google GenAI SDK with multi-model fallback chains e.g., `gemini-3.5-flash-lite`, `gemini-3.6-flash`, with Vertex AI regional pinning support).
2. `anthropic` (Claude 3.5/Opus via Anthropic SDK).
3. `ollama` (Local HTTP execution with models such as `qwen2.5:3b` or `llama3.2`).
4. `none` (Extractive fallback mode: synthesizes direct quote-only answers with zero external LLM dependencies).

Strict time budgets are assigned to classification, generation, and verification. If any stage exceeds its budget, it safely degrades to deterministic rule classification and extractive passage display.

## Consequences
- **Positive:** Zero vendor lock-in; seamless transition from cloud demo to air-gapped deployment.
- **Positive:** Graceful degradation during network or quota failures.
- **Negative:** Prompt templates must remain compatible across both frontier cloud LLMs and compact local models.
