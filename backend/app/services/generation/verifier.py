"""Independent citation verifier — the gate between a draft and the user (ADR 0003).

For every sentence ("claim") of the draft:
  1. No citation marker            → unsupported ("uncited").
  2. Markers that match no passage → ignored; none left → unsupported.
  3. Numeric guard (deterministic): every number in the claim must appear in at least one cited
     passage (its text or its citation metadata). This runs before, and regardless of, the judge.
  4. Judge: the LLM verifier prompt per (claim, cited passage) — supported if ANY cited passage
     returns supported=true with score >= VERIFIER_THRESHOLD. Without an LLM (or if it errors) a
     strict lexical judge is used instead. With NLI enabled, the NLI model must also entail.
Unsupported claims are removed; if no supported claim remains, the orchestrator abstains.
Quick values survive only if their value text appears in their source passage.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.generation.generator import Draft, Passage, glossary_block
from app.services.generation.prompts import PromptSet
from app.services.llm.base import LLMError, LLMProvider
from app.services.textutil import extract_numbers, split_lines, split_sentences, stemmed_words, strip_markers

VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "score": {"type": "number"},
        "issue": {"type": "string"},
    },
    "required": ["supported", "score", "issue"],
    "additionalProperties": False,
}

_MARKER = re.compile(r"\[(S\d+)\]")
# Words that describe citations rather than clinical content; ignored by the lexical judge.
_META_WORDS = frozenset(
    stemmed_words(
        "per according states stated says document documents section clause protocol circular guideline "
        "conflict conflicts between however later earlier more recent newer older effective date dated "
        "amends amended amendment version current note see also both value values"
    )
)
LEXICAL_MIN_COVERAGE = 0.75


class NLIChecker(Protocol):
    def entailment(self, premise: str, hypothesis: str) -> float: ...


@dataclass
class ClaimCheck:
    text: str
    markers: list[str]
    supported: bool
    score: float
    issue: str | None = None
    supported_by: str | None = None
    judge: str = "none"


@dataclass
class Verification:
    claims: list[ClaimCheck]
    answer: str
    quick_values: list[dict[str, str]]
    used_markers: list[str]
    dropped_quick_values: int = 0
    judge: str = "lexical"
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def supported_ratio(self) -> float:
        return sum(c.supported for c in self.claims) / len(self.claims) if self.claims else 0.0

    @property
    def has_supported_claims(self) -> bool:
        return any(c.supported for c in self.claims)


class _CombinedPassage:
    """Several cited passages judged together (a claim may join facts from two sources)."""

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self.marker = "+".join(p.marker for p in passages)

    @property
    def body(self) -> str:
        return "\n\n".join(p.body for p in self.passages)

    @property
    def metadata_numbers(self) -> set[str]:
        return set().union(*(p.metadata_numbers for p in self.passages))

    def render(self) -> str:
        return "\n\n".join(p.render() for p in self.passages)


def numeric_guard(claim: str, passages: list[Passage]) -> str | None:
    """Return an issue string if the claim contains a number not present in any cited passage."""
    claim_numbers = extract_numbers(claim)
    if not claim_numbers:
        return None
    allowed: set[str] = set()
    for p in passages:
        allowed |= extract_numbers(p.body) | p.metadata_numbers
    missing = sorted(claim_numbers - allowed)
    return f"number(s) not in cited passage: {', '.join(missing)}" if missing else None


def lexical_judge(claim: str, passage: Passage | _CombinedPassage) -> tuple[bool, float, str | None]:
    words = stemmed_words(strip_markers(claim)) - _META_WORDS
    if not words:
        return True, 1.0, None
    source = stemmed_words(passage.render())
    coverage = len(words & source) / len(words)
    if coverage >= LEXICAL_MIN_COVERAGE:
        return True, round(coverage, 3), None
    missing = sorted(words - source)[:5]
    return False, round(coverage, 3), f"terms not in passage: {', '.join(missing)}"


async def _llm_judge(
    llm: LLMProvider,
    prompts: PromptSet,
    claim: str,
    passage: Passage | _CombinedPassage,
    glossary: list[tuple[str, str]] | None = None,
) -> tuple[bool, float, str | None]:
    terms = "\n".join(glossary_block(glossary))
    data = await llm.complete_json(
        system=prompts.verifier.text,
        user=f"Passage:\n{passage.render()}\n\n{terms}Claim:\n{strip_markers(claim).strip()}",
        schema=VERIFIER_SCHEMA,
        task="verify",
        max_tokens=200,
    )
    supported = data.get("supported") is True
    try:
        score = float(data.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    issue = data.get("issue")
    return supported, max(0.0, min(1.0, score)), (str(issue) if issue else None)


BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "integer"},
                    "supported": {"type": "boolean"},
                    "score": {"type": "number"},
                    "issue": {"type": "string"},
                },
                "required": ["claim", "supported", "score", "issue"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

BATCH_INSTRUCTIONS = """

You will receive several numbered claims. Apply the rules above to EACH claim separately, using only
the passages that claim cites; never let one claim's passages support another claim.
Return JSON only: {"verdicts": [{"claim": <number>, "supported": true|false, "score": 0.0-1.0,
"issue": string}]} with exactly one verdict per claim (issue "" when supported)."""


async def _llm_judge_batch(
    llm: LLMProvider,
    prompts: PromptSet,
    pending: list[tuple[int, str, list[Passage]]],
    glossary: list[tuple[str, str]] | None = None,
) -> dict[int, tuple[bool, float, str | None]]:
    """One call judging every claim against its own cited passages (same rubric, per claim)."""
    passages: dict[str, Passage] = {}
    for _, _, cited in pending:
        for p in cited:
            passages.setdefault(p.marker, p)
    lines = ["Source passages:", *[p.render() + "\n" for p in passages.values()], *glossary_block(glossary), "Claims:"]
    for number, sentence, cited in pending:
        markers = ", ".join(p.marker for p in cited)
        lines.append(f"{number}. (cites {markers}) {strip_markers(sentence).strip()}")
    data = await llm.complete_json(
        system=prompts.verifier.text + BATCH_INSTRUCTIONS,
        user="\n".join(lines),
        schema=BATCH_SCHEMA,
        task="verify",
        max_tokens=120 * len(pending) + 100,
    )
    verdicts: dict[int, tuple[bool, float, str | None]] = {}
    for item in data.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        try:
            number = int(item.get("claim") or 0)
            score = max(0.0, min(1.0, float(item.get("score") or 0.0)))
        except (TypeError, ValueError):
            continue
        issue = item.get("issue")
        verdicts[number] = (item.get("supported") is True, score, str(issue) if issue else None)
    return verdicts


def _segment(answer: str) -> list[tuple[int, str, str]]:
    """[(line_index, bullet_prefix, sentence)] preserving the answer's line structure."""
    out: list[tuple[int, str, str]] = []
    for index, (prefix, body) in enumerate(split_lines(answer)):
        for sentence in split_sentences(body):
            out.append((index, prefix, sentence))
    return out


async def verify(
    draft: Draft,
    passages: list[Passage],
    *,
    llm: LLMProvider | None,
    prompts: PromptSet,
    threshold: float,
    nli: NLIChecker | None = None,
    mode: str = "batch",
    glossary: list[tuple[str, str]] | None = None,
) -> Verification:
    by_marker = {p.marker: p for p in passages}
    segments = _segment(draft.answer)
    judge_name = "llm" if llm is not None else "lexical"
    llm_failed = False
    batch_verdicts: dict[int, tuple[bool, float, str | None]] | None = None

    if llm is not None and mode == "batch":
        # Deterministic gates first; only claims that pass them are sent to the LLM (one call).
        pending: list[tuple[int, str, list[Passage]]] = []
        for number, (_, _, sentence) in enumerate(segments, start=1):
            markers = list(dict.fromkeys(_MARKER.findall(sentence)))
            cited = [by_marker[m] for m in markers if m in by_marker]
            if cited and numeric_guard(sentence, cited) is None:
                pending.append((number, sentence, cited))
        if pending:
            try:
                batch_verdicts = await _llm_judge_batch(llm, prompts, pending, glossary)
            except LLMError:
                llm_failed = True
        else:
            batch_verdicts = {}

    async def check(number: int, sentence: str) -> ClaimCheck:
        nonlocal llm_failed
        markers = list(dict.fromkeys(_MARKER.findall(sentence)))
        if not markers:
            return ClaimCheck(sentence, [], False, 0.0, "uncited")
        cited = [by_marker[m] for m in markers if m in by_marker]
        if not cited:
            return ClaimCheck(sentence, markers, False, 0.0, "cites an unknown source")
        issue = numeric_guard(sentence, cited)
        if issue:
            return ClaimCheck(sentence, markers, False, 0.0, issue, judge="numeric-guard")
        if batch_verdicts is not None:
            ok, score, why = batch_verdicts.get(number, (False, 0.0, "no verdict returned"))
            ok = ok and score >= threshold
            judge = "llm-batch"
            if ok and nli is not None:
                together = _CombinedPassage(cited) if len(cited) > 1 else cited[0]
                entail = await asyncio.to_thread(nli.entailment, together.render(), strip_markers(sentence))
                if entail < threshold:
                    ok, why = False, f"NLI entailment {entail:.2f} below threshold"
                judge += "+nli"
            return ClaimCheck(sentence, markers, ok, score, None if ok else why, cited[0].marker if ok else None, judge)
        best: ClaimCheck | None = None
        judged: list[Passage | _CombinedPassage] = list(cited)
        if len(cited) > 1:
            judged.append(_CombinedPassage(cited))  # last resort: the cited passages taken together
        for passage in judged:
            judge = "lexical"
            if llm is not None and not llm_failed:
                try:
                    ok, score, why = await _llm_judge(llm, prompts, sentence, passage, glossary)
                    judge = "llm"
                except LLMError:
                    llm_failed = True
                    ok, score, why = lexical_judge(sentence, passage)
            else:
                ok, score, why = lexical_judge(sentence, passage)
            ok = ok and score >= (threshold if judge == "llm" else LEXICAL_MIN_COVERAGE)
            if ok and nli is not None:
                entail = await asyncio.to_thread(nli.entailment, passage.render(), strip_markers(sentence))
                if entail < threshold:
                    ok, why = False, f"NLI entailment {entail:.2f} below threshold"
                judge += "+nli"
            supported_by = (passage.marker.split("+")[0]) if ok else None
            result = ClaimCheck(sentence, markers, ok, score, None if ok else why, supported_by, judge)
            if ok:
                return result
            if best is None or result.score > best.score:
                best = result
        assert best is not None
        return best

    checks = list(
        await asyncio.gather(*(check(number, sentence) for number, (_, _, sentence) in enumerate(segments, start=1)))
    )

    # Rebuild the answer from supported claims, keeping bullets / line breaks.
    lines: dict[int, list[str]] = {}
    prefixes: dict[int, str] = {}
    for (line_index, prefix, _), result in zip(segments, checks, strict=True):
        prefixes[line_index] = prefix
        if result.supported:
            lines.setdefault(line_index, []).append(result.text)
    answer = "\n".join(prefixes[i] + " ".join(lines[i]) for i in sorted(lines))
    used = list(dict.fromkeys(m for m in _MARKER.findall(answer) if m in by_marker))

    kept_quick: list[dict[str, str]] = []
    for qv in draft.quick_values:
        source = (qv.get("source") or "").strip("[] ")
        passage = by_marker.get(source)
        value = (qv.get("value") or "").strip()
        if not passage or not value:
            continue
        haystack = " ".join(passage.body.lower().split())
        needle = " ".join(value.lower().split())
        numbers_ok = extract_numbers(value) <= extract_numbers(passage.body)
        if needle in haystack or (numbers_ok and extract_numbers(value)):
            kept_quick.append({"label": qv.get("label", ""), "value": value, "source": source})
            if source not in used:
                used.append(source)
    if llm_failed:
        judge_name = "lexical (llm unavailable)"
    summary = {
        "claims": len(checks),
        "supported": sum(c.supported for c in checks),
        "judge": judge_name + ("+nli" if nli is not None else ""),
        "threshold": threshold,
        "dropped": [{"claim": c.text[:300], "issue": c.issue} for c in checks if not c.supported],
    }
    return Verification(
        claims=checks,
        answer=answer,
        quick_values=kept_quick,
        used_markers=used,
        dropped_quick_values=len(draft.quick_values) - len(kept_quick),
        judge=judge_name,
        summary=summary,
    )


class CrossEncoderNLI:
    """cross-encoder/nli-deberta-v3-base: labels (contradiction, entailment, neutral)."""

    def __init__(self, model_name: str) -> None:
        self.model_id = model_name
        self._model: Any = None

    def entailment(self, premise: str, hypothesis: str) -> float:
        import numpy as np

        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_id, device="cpu")
        logits = np.asarray(self._model.predict([(premise, hypothesis)], apply_softmax=False))[0]
        probs = np.exp(logits - logits.max())
        probs = probs / probs.sum()
        return float(probs[1])
