"""Small text helpers shared by retrieval, generation and verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "per",
        "please",
        "should",
        "so",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "this",
        "those",
        "to",
        "under",
        "up",
        "upon",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "within",
        "would",
        "you",
        "your",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "any",
        "because",
        "before",
        "below",
        "between",
        "both",
        "during",
        "each",
        "few",
        "further",
        "here",
        "more",
        "most",
        "no",
        "nor",
        "not",
        "only",
        "other",
        "out",
        "over",
        "same",
        "some",
        "still",
        "very",
        "tell",
        "show",
        "give",
        "list",
        "explain",
        "according",
        "say",
        "says",
        "said",
        "current",
        "currently",
        "latest",
        "new",
        "old",
    ]
)

_UNIT = (
    r"units?/kg/h(?:r|our)?|units?/kg|units?/h(?:r|our)?|units?|iu|ml/kg/h(?:r)?|ml/kg|ml/h(?:r|our)?|ml|"
    r"l/min|l|mg/kg/day|mg/kg|mg/h|mg|mcg/kg/min|mcg/kg|mcg|µg|g/l|g/dl|g|mmol/l|mmol/h|mmol|meq/l|meq|"
    r"hours?|hrs?|h|minutes?|mins?|min|seconds?|secs?|s|days?|weeks?|%|mmhg|°c|kg|x ?10\^?9/l|"
    r"packs?|doses?|times?|bags?|vials?|bottles?|beds?"
)
_QUANTITY = re.compile(
    rf"(?<![\w.])([<>≥≤]=?\s*)?(\d{{1,3}}(?:,\d{{3}})+|\d+(?:\.\d+)?)(?:\s*(?:–|-|to)\s*(\d+(?:\.\d+)?))?\s*({_UNIT})?(?![\w])",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")
_MARKER = re.compile(r"\[S\d+\]")
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*")


@dataclass(frozen=True)
class Quantity:
    value: str  # normalised number (or range "a-b")
    unit: str  # normalised unit ("" if none)
    start: int
    end: int
    raw: str


def normalize_number(raw: str) -> str:
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return raw
    normalized = value.normalize()
    text = format(normalized, "f")
    return text


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.lower().replace(" ", "")
    aliases = {
        "hour": "h",
        "hours": "h",
        "hr": "h",
        "hrs": "h",
        "minute": "min",
        "minutes": "min",
        "mins": "min",
        "second": "s",
        "seconds": "s",
        "sec": "s",
        "secs": "s",
        "day": "day",
        "days": "day",
        "week": "week",
        "weeks": "week",
        "unit": "units",
        "iu": "units",
        "units/kg/hr": "units/kg/h",
        "units/kg/hour": "units/kg/h",
        "unit/kg/h": "units/kg/h",
        "unit/kg": "units/kg",
        "units/hr": "units/h",
        "units/hour": "units/h",
        "ml/hr": "ml/h",
        "ml/hour": "ml/h",
        "pack": "packs",
        "dose": "doses",
        "time": "times",
    }
    return aliases.get(u, u)


def strip_markers(text: str) -> str:
    return _MARKER.sub("", text)


def extract_quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    clean = strip_markers(text)
    for match in _QUANTITY.finditer(clean):
        low = normalize_number(match.group(2))
        high = match.group(3)
        value = f"{low}-{normalize_number(high)}" if high else low
        out.append(Quantity(value, normalize_unit(match.group(4)), match.start(), match.end(), match.group(0).strip()))
    return out


def extract_numbers(text: str) -> set[str]:
    """Every number in the text, normalised (citation markers removed)."""
    return {normalize_number(m.group()) for m in _NUMBER.finditer(strip_markers(text))}


def content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if w.lower() not in STOPWORDS and len(w) > 1}


def stem(word: str) -> str:
    """Tiny suffix stripper: rates/rate, reduced/reduce/reduces and change/changes/changed agree."""
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) >= 5:
        word = word[:-1]
    return word


def stemmed_words(text: str) -> set[str]:
    return {stem(w) for w in content_words(text)}


_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+")
_BOUNDARY = re.compile(r"(?<=[.!?])((?:\s*\[S\d+\])*)\s+(?=[A-Z0-9\"'(])")


def split_sentences(line: str) -> list[str]:
    """Split one line into sentences; citation markers after the full stop stay with their sentence."""
    line = " ".join(line.split())
    if not line:
        return []
    sentences: list[str] = []
    cursor = 0
    for match in _BOUNDARY.finditer(line):
        end = match.end(1)
        sentences.append(line[cursor:end].strip())
        cursor = match.end()
    tail = line[cursor:].strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]


def split_lines(text: str) -> list[tuple[str, str]]:
    """Answer text -> [(bullet_prefix, line_body)] for non-empty lines."""
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        match = _BULLET.match(raw)
        prefix = match.group(0).strip() + " " if match else ""
        out.append((prefix, raw[match.end() :] if match else raw.strip()))
    return out
