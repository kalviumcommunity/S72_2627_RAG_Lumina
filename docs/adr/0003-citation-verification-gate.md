# ADR 0003: Mandatory Independent Citation Verification Gate

## Status
Accepted

## Context
In healthcare systems, generative LLMs can produce subtle hallucinations (e.g., misstating an infusion adjustment by a single unit or confusing IV with IM administration) while writing in an authoritative clinical tone. Simply instructing the generator model to "cite its sources" is insufficient to prevent hallucinated clinical details.

## Decision
We enforce a hard, independent verification gate between answer generation and user delivery:
1. Every generated clinical assertion must be annotated with source markers (`[S1]`, `[S2]`).
2. The answer is parsed into atomic claims.
3. An independent verification judge evaluates each claim against the exact cited passage text with a strict rubric: every drug, dose, unit, and condition must be directly entailed.
4. Unsupported claims are pruned from the response.
5. If zero supported clinical claims remain after pruning, the system withholds the response and returns a structured `not_found` abstention.
6. In streaming mode, answer text is withheld until the verification pass completes.

## Consequences
- **Positive:** Uncited or unsupported clinical claims are completely blocked from reaching end users.
- **Positive:** Verifiable audit trail where every displayed sentence has an associated verification score.
- **Negative:** Adds a secondary verification latency step (~800ms - 1.5s).
