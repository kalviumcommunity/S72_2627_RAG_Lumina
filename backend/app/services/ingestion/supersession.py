"""Effective-version resolution and supersession logic (pure functions, fully unit-tested).

Effective-version rule
----------------------
* The *current* version of a document is the `approved` version with the latest
  `effective_from <= as_of` (ties broken by the latest `approved_at`).
* A chunk is *superseded* when a confirmed supersession targets its document (and a section path
  that is a prefix of any path the chunk covers, if the link names a section), the link's
  `effective_from <= as_of`, and the link's source version is approved — or was approved and later
  replaced by a newer version of the same amending document (status `superseded`). A draft or
  retired source never supersedes anything (ADR 0003).

The SQL used by retrieval (retrieval/eligibility.py) implements the same rule; integration tests
check the two agree.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.models.enums import VersionStatus

ACTIVE_SOURCE_STATUSES = frozenset({VersionStatus.approved, VersionStatus.superseded})


@dataclass(frozen=True)
class VersionInfo:
    id: uuid.UUID
    document_id: uuid.UUID
    status: VersionStatus
    effective_from: date
    approved_at: datetime | None = None


@dataclass(frozen=True)
class SupersessionInfo:
    source_version_id: uuid.UUID
    source_status: VersionStatus
    target_document_id: uuid.UUID
    target_section_path: str | None
    effective_from: date
    confirmed: bool


def current_version(versions: Iterable[VersionInfo], as_of: date) -> VersionInfo | None:
    eligible = [v for v in versions if v.status == VersionStatus.approved and v.effective_from <= as_of]
    if not eligible:
        return None
    return max(eligible, key=lambda v: (v.effective_from, v.approved_at or datetime.min))


def current_versions_by_document(versions: Iterable[VersionInfo], as_of: date) -> dict[uuid.UUID, VersionInfo]:
    grouped: dict[uuid.UUID, list[VersionInfo]] = {}
    for version in versions:
        grouped.setdefault(version.document_id, []).append(version)
    result: dict[uuid.UUID, VersionInfo] = {}
    for doc_id, items in grouped.items():
        current = current_version(items, as_of)
        if current is not None:
            result[doc_id] = current
    return result


def section_matches(target: str | None, path: str) -> bool:
    """True if `path` is the targeted section or inside it (4.2 matches 4.2, 4.2.1, 4.2#1, 4.2(a))."""
    if target is None:
        return True
    target = target.strip()
    return path == target or any(path.startswith(target + sep) for sep in (".", "#", "("))


def is_active(link: SupersessionInfo, as_of: date) -> bool:
    return link.confirmed and link.effective_from <= as_of and link.source_status in ACTIVE_SOURCE_STATUSES


def is_superseded(
    document_id: uuid.UUID,
    covered_paths: Sequence[str],
    links: Iterable[SupersessionInfo],
    as_of: date,
) -> bool:
    for link in links:
        if link.target_document_id != document_id or not is_active(link, as_of):
            continue
        if any(section_matches(link.target_section_path, path) for path in covered_paths):
            return True
    return False


# --------------------------------------------------------------------------------------------------
# Reference detection in amending documents (circulars)
# --------------------------------------------------------------------------------------------------

DOC_CODE_IN_TEXT = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,6}){1,3})\b")
SECTION_REF = re.compile(r"(?:§\s*|\bsection\s+|\bclause\s+|\bpara(?:graph)?\s+)(\d{1,2}(?:\.\d{1,2}){0,4})", re.I)
TRIGGER = re.compile(
    r"\b(supersed\w*|amend\w*|replac\w*|revok\w*|withdraw\w*|substitut\w*|in\s+partial\s+modification\s+of|"
    r"modif\w*|rescind\w*|stands?\s+cancelled|no\s+longer\s+appl\w*)",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.;])\s+|\n{2,}")
_TABLE_RULE = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|?)+$")


def _flatten_tables(text: str) -> str:
    """Markdown table rows become standalone sentences ("Amends: P-ICU-07 §4.2") so the evidence
    shown to approvers is the row that matters, not the whole header table."""
    lines: list[str] = []
    for line in text.splitlines():
        row = line.strip()
        if not (row.startswith("|") and row.endswith("|")):
            lines.append(line)
            continue
        if _TABLE_RULE.match(row):
            continue
        cells = [c.strip() for c in row.strip("|").split("|") if c.strip()]
        if cells:
            lines += [f"{cells[0]}: {' · '.join(cells[1:])}" if len(cells) > 1 else cells[0], ""]
    return "\n".join(lines)


@dataclass(frozen=True)
class SupersessionSuggestion:
    target_doc_code: str
    target_section_path: str | None
    evidence: str


def detect_references(text: str, known_doc_codes: Iterable[str], self_code: str) -> list[SupersessionSuggestion]:
    """Find "amends P-ICU-07 §4.2"-style statements. A bare citation without a trigger word is ignored."""
    known = {c.upper() for c in known_doc_codes} - {self_code.upper()}
    found: dict[tuple[str, str | None], SupersessionSuggestion] = {}
    for sentence in _SENTENCE.split(_flatten_tables(text)):
        sentence = " ".join(sentence.split())
        if not sentence or not TRIGGER.search(sentence):
            continue
        codes = [m for m in DOC_CODE_IN_TEXT.finditer(sentence) if m.group(1).upper() in known]
        for code_match in codes:
            code = code_match.group(1).upper()
            # Section references that follow this code (before the next document code).
            following = sentence[code_match.end() :]
            next_code = DOC_CODE_IN_TEXT.search(following)
            window = following[: next_code.start()] if next_code else following
            sections = [m.group(1) for m in SECTION_REF.finditer(window)]
            if not sections:  # "section 4.2 of P-ICU-07" — reference before the code
                preceding = sentence[: code_match.start()]
                sections = [m.group(1) for m in SECTION_REF.finditer(preceding)][-1:]
            targets: list[str | None] = list(dict.fromkeys(sections)) or [None]
            for section in targets:
                found.setdefault((code, section), SupersessionSuggestion(code, section, sentence[:500]))
    return list(found.values())
