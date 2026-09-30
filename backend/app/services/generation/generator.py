"""Grounded answer generation with [S#] citation markers.

LLM mode uses prompts/generator.md. Extractive mode (no LLM configured, or the LLM call failed)
quotes the best-matching sentences / table rows of the top passage verbatim — trivially grounded,
and still passed through the verifier like any other draft.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.generation.prompts import PromptSet
from app.services.llm.base import LLMError, LLMProvider
from app.services.retrieval.types import Candidate
from app.services.textutil import extract_numbers, extract_quantities, stemmed_words

GENERATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "quick_values": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["label", "value", "source"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "quick_values"],
    "additionalProperties": False,
}

NOT_FOUND = "NOT_FOUND"


@dataclass
class Passage:
    marker: str  # "S1"
    candidate: Candidate

    @property
    def header(self) -> str:
        c = self.candidate
        return (
            f'[{self.marker}] {c.doc_code} "{c.title}" v{c.version_label} §{c.section_path}, '
            f"p.{c.page_start}, effective {c.effective_from.isoformat()}"
        )

    @property
    def body(self) -> str:
        c = self.candidate
        amends = "; ".join(
            f"{a['doc_code']}" + (f" §{a['section_path']}" if a.get("section_path") else "") for a in c.supersedes
        )
        note = f"(This document amends {amends})\n" if amends else ""
        return f"{note}{c.heading}\n{c.text}"

    @property
    def metadata_numbers(self) -> set[str]:
        """Numbers that legitimately appear in citations of this passage (codes, section, version, date)."""
        c = self.candidate
        return extract_numbers(f"{c.doc_code} {c.section_path} {c.version_label} {c.effective_from.isoformat()}")

    def render(self) -> str:
        return f"{self.header}\n{self.body}"


@dataclass
class ConflictNote:
    marker_a: str
    marker_b: str
    description: str


@dataclass
class Draft:
    answer: str
    quick_values: list[dict[str, str]] = field(default_factory=list)
    not_found: bool = False
    mode: Literal["llm", "extractive"] = "llm"
    llm_error: str | None = None


def build_passages(candidates: list[Candidate]) -> list[Passage]:
    return [Passage(f"S{i}", c) for i, c in enumerate(candidates, start=1)]


def glossary_block(glossary: list[tuple[str, str]] | None) -> list[str]:
    """Matched entries of the hospital's approved abbreviation / brand-name list (not model knowledge)."""
    if not glossary:
        return []
    return [
        "Glossary from the hospital's approved abbreviation list (treat these terms as equivalent):",
        *[f"- {term} = {meaning}" for term, meaning in glossary],
        "",
    ]


def build_user_prompt(
    question: str,
    passages: list[Passage],
    conflicts: list[ConflictNote],
    glossary: list[tuple[str, str]] | None = None,
) -> str:
    parts = ["Source passages:", *[p.render() + "\n" for p in passages], *glossary_block(glossary)]
    if conflicts:
        parts.append("Possible conflicts detected between passages (state both values, do not choose):")
        parts += [f"- [{c.marker_a}] vs [{c.marker_b}]: {c.description}" for c in conflicts]
        parts.append("")
    parts.append(f"Question: {question}")
    return "\n".join(parts)


# Scores (question, texts) pairs for relevance, e.g. the retrieval cross-encoder; 0..1 per text.
UnitScorer = Callable[[str, list[str]], list[float]]


async def generate(
    question: str,
    passages: list[Passage],
    conflicts: list[ConflictNote],
    llm: LLMProvider | None,
    prompts: PromptSet,
    key_terms: set[str] | None = None,
    glossary: list[tuple[str, str]] | None = None,
    unit_scorer: UnitScorer | None = None,
) -> Draft:
    def extractive() -> Draft:
        return extractive_answer(question, passages, conflicts, key_terms, glossary, unit_scorer)

    if llm is None:
        return await asyncio.to_thread(extractive)
    try:
        data = await llm.complete_json(
            system=prompts.generator.text,
            user=build_user_prompt(question, passages, conflicts, glossary),
            schema=GENERATOR_SCHEMA,
            task="generate",
            max_tokens=700,
        )
    except LLMError as exc:
        draft = await asyncio.to_thread(extractive)
        draft.llm_error = str(exc)
        return draft
    answer = str(data.get("answer") or "").strip()
    if not answer or answer.strip().upper().startswith(NOT_FOUND):
        return Draft(answer="", not_found=True, mode="llm")
    quick = [
        {
            "label": str(q.get("label", ""))[:80],
            "value": str(q.get("value", ""))[:120],
            "source": str(q.get("source", "")),
        }
        for q in (data.get("quick_values") or [])
        if isinstance(q, dict)
    ]
    return Draft(answer=answer, quick_values=quick[:6], mode="llm")


# --------------------------------------------------------------------------------------------------
# Extractive fallback
# --------------------------------------------------------------------------------------------------

_MD_NOISE = re.compile(r"\*\*|__|`|^\s*>\s?|^\s*(?:[-*+•]|\d{1,2}[.)])\s+", re.MULTILINE)
_NEW_ITEM = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)]|\([a-z]{1,2}\)|\([ivx]{1,5}\))\s+")


@dataclass
class _Unit:
    passage: Passage
    order: int
    text: str
    row: dict[str, str] | None = None
    lead: _Unit | None = None  # for a table row: the sentence introducing the table


def _clean(text: str) -> str:
    return " ".join(_MD_NOISE.sub("", text).split())


def _units(passage: Passage, start_order: int = 0) -> list[_Unit]:
    """Sentences and table rows ("Heading — Header: cell; …") of a passage, in document order.

    Wrapped lines (PDF/OCR text) are joined back into paragraphs; list items stay separate."""
    candidate = passage.candidate
    units: list[_Unit] = []
    header: list[str] | None = None
    lead: _Unit | None = None
    paragraph: list[str] = []
    order = start_order

    def flush() -> None:
        nonlocal paragraph, order
        if not paragraph:
            return
        clean = _clean(" ".join(paragraph))
        paragraph = []
        for sentence in re.split(r"(?<=[.;])\s+(?=[A-Z(])", clean):
            if len(sentence.split()) >= 3:
                units.append(_Unit(passage, order, sentence.rstrip()))
                order += 1

    for line in candidate.text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            flush()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue
            if header is None:
                header = cells
                lead = units[-1] if units and units[-1].row is None else None
                continue
            pairs = {_clean(h): _clean(v) for h, v in zip(header, cells, strict=False) if v}
            body = "; ".join(f"{h}: {v}" for h, v in pairs.items())
            units.append(_Unit(passage, order, f"{candidate.heading} — {body}", pairs, lead))
            order += 1
            continue
        header = None
        if not stripped:
            flush()
            continue
        if _NEW_ITEM.match(stripped):
            flush()
        paragraph.append(stripped)
    flush()
    return units


def _unit_words(unit: _Unit) -> set[str]:
    # The clause heading and document title give a unit its subject ("Loading bolus" → heparin).
    c = unit.passage.candidate
    return stemmed_words(f"{unit.text} {c.heading} {c.title}")


@dataclass(frozen=True)
class _Query:
    """What the question asks for, with approved abbreviation expansions folded in.

    Each concept is one question word plus its alternatives: "MTP" is matched by text that says
    "MTP" or "massive transfusion protocol"; "UFH" by "unfractionated heparin"."""

    concepts: tuple[tuple[frozenset[str], ...], ...]
    numbers: frozenset[str]
    key_terms: tuple[tuple[frozenset[str], ...], ...]
    asks_why: bool
    asks_metadata: bool

    @property
    def words(self) -> set[str]:
        return {w for alternatives in self.concepts for alt in alternatives for w in alt}


def _alternatives(word: str, glossary: list[tuple[str, str]]) -> tuple[frozenset[str], ...]:
    alts = [frozenset({word})]
    for term, meaning in glossary:
        t, m = stemmed_words(term), stemmed_words(meaning)
        if word in t and m:
            alts.append(frozenset(m))
        elif word in m and t:
            alts.append(frozenset(t))
    return tuple(alts)


def _parse_query(question: str, key_terms: set[str], glossary: list[tuple[str, str]]) -> _Query:
    words = stemmed_words(question)
    return _Query(
        concepts=tuple(_alternatives(w, glossary) for w in sorted(words)),
        numbers=frozenset(extract_numbers(question)),
        key_terms=tuple(_alternatives(k, glossary) for k in sorted(key_terms)),
        asks_why=bool(re.search(r"\b(why|purpose|background|reason|rationale)\b", question, re.I)),
        asks_metadata=bool(re.search(r"\b(effective|version|issued|owner|review due|date of)\b", question, re.I)),
    )


def _matched(concepts: tuple[tuple[frozenset[str], ...], ...], words: set[str]) -> int:
    return sum(any(alt <= words for alt in alternatives) for alternatives in concepts)


# Headings that explain why a document exists rather than what to do; rarely the answer.
_CONTEXT_HEADING = re.compile(r"^(background|purpose|introduction|rationale|document information)\b", re.I)


def _lexical_score(unit: _Unit, query: _Query) -> float:
    words = _unit_words(unit)
    overlap = _matched(query.concepts, words) / (len(query.concepts) or 1)
    number_bonus = 0.8 if query.numbers and query.numbers & extract_numbers(unit.text) else 0.0
    key_bonus = 0.6 * _matched(query.key_terms, words) / len(query.key_terms) if query.key_terms else 0.0
    return overlap + number_bonus + key_bonus + 0.5 * unit.passage.candidate.rerank_score


def _prior(unit: _Unit, query: _Query) -> float:
    c = unit.passage.candidate
    prior = 0.0
    if not c.applies_to_all_branches:
        prior += 0.3  # the user's own branch arrangements take precedence (eligibility checked the branch)
    if _CONTEXT_HEADING.match(c.heading.strip()) and not query.asks_why:
        prior -= 0.35
    if c.section_path == "0" and not query.asks_metadata:
        prior -= 0.35  # document header table / disclaimer
    return prior


def _sentence(text: str, marker: str) -> str:
    return f"{text.rstrip(' ;.')}. [{marker}]"


def extractive_answer(
    question: str,
    passages: list[Passage],
    conflicts: list[ConflictNote],
    key_terms: set[str] | None = None,
    glossary: list[tuple[str, str]] | None = None,
    unit_scorer: UnitScorer | None = None,
) -> Draft:
    """Quote the best-matching sentences / table rows verbatim (no LLM).

    Candidates are scored lexically (question concepts incl. approved abbreviations, numbers named in
    the question, key terms), by passage relevance and document authority, and — when a relevance
    model is available — by the cross-encoder at sentence level, so "Pack 1" picks the pack table
    rather than a sentence that merely mentions units of blood."""
    if not passages:
        return Draft(answer="", not_found=True, mode="extractive")
    glossary = glossary or []
    query = _parse_query(question, key_terms or set(), glossary)
    considered = list(passages[:3])
    if query.key_terms:  # passages that name the specific thing asked about are always considered
        considered += [
            p
            for p in passages[3:]
            if _matched(query.key_terms, stemmed_words(f"{p.candidate.heading} {p.candidate.text} {p.candidate.title}"))
        ]
    units: list[_Unit] = []
    for passage in considered:
        units += _units(passage, start_order=len(units))
    if query.key_terms:
        # A specific thing was asked about: only quote text that names it (else abstain).
        units = [u for u in units if _matched(query.key_terms, _unit_words(u))]
    if not units or max(_lexical_score(u, query) for u in units) < 0.34:
        return Draft(answer="", not_found=True, mode="extractive")

    semantic = [0.0] * len(units)
    if unit_scorer is not None:
        expansions = "; ".join(f"{t} = {m}" for t, m in glossary)
        probe = f"{question} ({expansions})" if expansions else question
        try:
            semantic = unit_scorer(probe, [f"{u.passage.candidate.heading}: {u.text}" for u in units])
        except Exception:  # noqa: BLE001  the relevance model is an optional refinement
            semantic = [0.0] * len(units)
    scored = sorted(
        ((u, _lexical_score(u, query) + _prior(u, query) + 1.5 * s) for u, s in zip(units, semantic, strict=True)),
        key=lambda x: -x[1],
    )
    best_unit, best_score = scored[0]

    def number_match(u: _Unit) -> bool:
        return bool(query.numbers & extract_numbers(u.text))

    companions = [
        u
        for u, s in scored[1:4]
        if u.passage is best_unit.passage
        and s >= 0.75 * best_score
        # When the question names a value (e.g. "aPTT above 100"), quote only the matching rows.
        and (not query.numbers or number_match(u) == number_match(best_unit))
    ]
    chosen = [best_unit, *companions[:2]]
    # A table row quoted alone can lose its rule ("Vancomycin: IV" without "approval within 24
    # hours"): add the table's lead-in sentence when it covers question words the rows do not.
    covered = set().union(*(_unit_words(u) for u in chosen))
    for unit in list(chosen):
        lead = unit.lead
        if lead is not None and lead not in chosen and (_unit_words(lead) & query.words) - covered:
            chosen.append(lead)
            covered |= _unit_words(lead)
    chosen.sort(key=lambda u: u.order)
    marker = best_unit.passage.marker
    lines = [_sentence(u.text, marker) for u in chosen]
    quick: list[dict[str, str]] = []
    for unit in chosen:
        if unit.row:
            quick += [{"label": k, "value": v, "source": marker} for k, v in list(unit.row.items())[1:4]]
        else:
            for q in extract_quantities(unit.text)[:2]:
                if q.unit:
                    label_words = re.findall(r"[A-Za-z]+", unit.text[: q.start])[-3:]
                    quick.append({"label": " ".join(label_words) or "Value", "value": q.raw, "source": marker})

    by_marker = {p.marker: p for p in passages}
    for note in conflicts:
        a, b = by_marker.get(note.marker_a), by_marker.get(note.marker_b)
        if not a or not b or marker not in (a.marker, b.marker):
            continue
        other = b if a.marker == marker else a
        other_units = sorted(_units(other), key=lambda u: -(_lexical_score(u, query) + _prior(u, query)))
        if not other_units:
            continue
        c = other.candidate
        lines.append(_sentence(f"However, {c.doc_code} §{c.section_path} states: {other_units[0].text}", other.marker))
        newer = a if a.candidate.effective_from >= b.candidate.effective_from else b
        lines.append(
            _sentence(
                f"{newer.candidate.doc_code} has the later effective date "
                f"({newer.candidate.effective_from.isoformat()})",
                newer.marker,
            )
        )
    return Draft(answer="\n".join(lines), quick_values=quick[:4], mode="extractive")
