"""Contradiction detection between passages of different documents.

`heuristic_conflict` finds quantities with the same unit whose surrounding words overlap but whose
values differ ("repeat aPTT 6 hours after a rate change" vs "check aPTT 4 hours after any rate
change"). It is the prefilter for the LLM judge at ingest time and the whole check at query time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.llm.base import LLMError, LLMProvider
from app.services.textutil import STOPWORDS, extract_quantities, stem

CONFLICT_SYSTEM = """You compare two passages taken from DIFFERENT approved hospital documents.
Decide whether they give contradictory instructions about the SAME concrete value: a dose, rate,
time interval, threshold, contact number, or who must approve something.
Complementary details, different patient groups, or different topics are NOT contradictions.
Return JSON only: {"contradicts": true|false, "confidence": 0.0-1.0, "description": string}
The description names the value each passage gives, e.g. "aPTT recheck: 6 h (A) vs 4 h (B)"."""

CONFLICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contradicts": {"type": "boolean"},
        "confidence": {"type": "number"},
        "description": {"type": "string"},
    },
    "required": ["contradicts", "confidence", "description"],
    "additionalProperties": False,
}

_WORDS = re.compile(r"[A-Za-z][A-Za-z-]+")
_IGNORED_UNITS = {"", "beds", "times"}
# Words too generic to show two quantities describe the same step (diluents, units, routes).
_GENERIC_CONTEXT = frozenset(
    stem(w)
    for w in [
        "sodium",
        "chloride",
        "glucose",
        "dextrose",
        "water",
        "saline",
        "units",
        "unit",
        "ml",
        "mls",
        "mmol",
        "seconds",
        "second",
        "minutes",
        "minute",
        "hours",
        "hour",
        "dose",
        "doses",
        "rate",
        "rates",
        "infusion",
        "infusions",
        "intravenous",
        "iv",
        "oral",
        "give",
        "given",
        "use",
        "used",
        "maximum",
        "minimum",
        "standard",
        "concentration",
        "table",
        "below",
        "above",
        "least",
        "more",
        "less",
        "than",
        "every",
        "each",
        "any",
        "all",
    ]
)


@dataclass(frozen=True)
class ConflictFinding:
    contradicts: bool
    confidence: float
    description: str
    value_a: str = ""
    value_b: str = ""


def _context(text: str, start: int, end: int, before: int = 8, after: int = 4) -> set[str]:
    left = _WORDS.findall(text[:start])[-before:]
    right = _WORDS.findall(text[end:])[:after]
    words = {stem(w.lower()) for w in left + right if w.lower() not in STOPWORDS and len(w) > 2}
    return words - _GENERIC_CONTEXT


def _snippet(text: str, start: int, end: int, width: int = 60) -> str:
    s = max(0, start - width)
    e = min(len(text), end + 20)
    return ("…" if s else "") + " ".join(text[s:e].split()) + ("…" if e < len(text) else "")


def heuristic_conflict(text_a: str, text_b: str, *, min_overlap: int = 2) -> ConflictFinding:
    qa = [q for q in extract_quantities(text_a) if q.unit not in _IGNORED_UNITS]
    qb = [q for q in extract_quantities(text_b) if q.unit not in _IGNORED_UNITS]
    values_a = {(q.unit, q.value) for q in qa}
    values_b = {(q.unit, q.value) for q in qb}
    best: ConflictFinding | None = None
    best_overlap = 0
    for a in qa:
        ctx_a = _context(text_a, a.start, a.end)
        for b in qb:
            if a.unit != b.unit or a.value == b.value:
                continue
            # Both passages mention the other's value too -> they are listing options, not disagreeing.
            if (b.unit, b.value) in values_a or (a.unit, a.value) in values_b:
                continue
            overlap = len(ctx_a & _context(text_b, b.start, b.end))
            if overlap >= min_overlap and overlap > best_overlap:
                best_overlap = overlap
                shared = ", ".join(sorted(ctx_a & _context(text_b, b.start, b.end))[:4])
                best = ConflictFinding(
                    contradicts=True,
                    confidence=min(0.95, 0.6 + 0.07 * overlap),
                    description=f"Different values for the same step ({shared}): "
                    f"“{_snippet(text_a, a.start, a.end)}” vs “{_snippet(text_b, b.start, b.end)}”",
                    value_a=a.raw,
                    value_b=b.raw,
                )
    return best or ConflictFinding(False, 0.0, "")


async def judge_conflict(
    llm: LLMProvider | None, label_a: str, text_a: str, label_b: str, text_b: str
) -> ConflictFinding:
    """Heuristic prefilter; if it fires and an LLM is configured, the LLM confirms or rejects."""
    heuristic = heuristic_conflict(text_a, text_b)
    if not heuristic.contradicts or llm is None:
        return heuristic
    user = f"Passage A ({label_a}):\n{text_a}\n\nPassage B ({label_b}):\n{text_b}"
    try:
        data = await llm.complete_json(
            system=CONFLICT_SYSTEM, user=user, schema=CONFLICT_SCHEMA, task="conflict", max_tokens=300
        )
    except LLMError:
        return heuristic
    return ConflictFinding(
        contradicts=bool(data.get("contradicts")),
        confidence=float(data.get("confidence") or 0.0),
        description=str(data.get("description") or heuristic.description)[:1000],
        value_a=heuristic.value_a,
        value_b=heuristic.value_b,
    )
