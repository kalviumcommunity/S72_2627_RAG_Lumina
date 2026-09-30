"""Query normalisation: expand clinical abbreviations and brand names (OD, TDS, SOS, Tazocin → …)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DICT_FILE = Path(__file__).with_name("abbreviations.yaml")


@dataclass(frozen=True)
class Abbreviation:
    term: str
    expansion: str
    case_sensitive: bool
    pattern: re.Pattern[str]


@dataclass
class ExpandedQuery:
    original: str
    text: str  # original + appended expansions (used for embedding / re-ranking)
    expansions: list[tuple[str, str]] = field(default_factory=list)

    @property
    def keyword_text(self) -> str:
        """OR-joined terms for websearch_to_tsquery (natural questions would AND every word)."""
        words = re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", self.text)
        seen: dict[str, None] = {}
        for w in words:
            if len(w) > 1 or w.isdigit():
                seen.setdefault(w.lower(), None)
        return " or ".join(seen)


@lru_cache
def load_abbreviations(path: str = str(_DICT_FILE)) -> tuple[Abbreviation, ...]:
    raw: dict[str, dict[str, Any]] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    items: list[Abbreviation] = []
    for group in raw.values():
        for term, spec in (group or {}).items():
            case_sensitive = bool(spec.get("case_sensitive", False))
            escaped = re.escape(str(term)).replace(r"\ ", r"[\s-]?")
            pattern = re.compile(rf"(?<![\w-]){escaped}(?![\w-])", 0 if case_sensitive else re.IGNORECASE)
            items.append(Abbreviation(str(term), str(spec["expansion"]), case_sensitive, pattern))
    # Longer terms first so "pip taz" wins over shorter overlapping entries.
    return tuple(sorted(items, key=lambda a: -len(a.term)))


def expand_query(question: str) -> ExpandedQuery:
    expansions: list[tuple[str, str]] = []
    seen_expansions: set[str] = set()
    for abbr in load_abbreviations():
        if abbr.pattern.search(question) and abbr.expansion.lower() not in seen_expansions:
            if abbr.expansion.lower() in question.lower():
                continue
            expansions.append((abbr.term, abbr.expansion))
            seen_expansions.add(abbr.expansion.lower())
    text = question if not expansions else f"{question} ({'; '.join(e for _, e in expansions)})"
    return ExpandedQuery(original=question, text=text, expansions=expansions)
