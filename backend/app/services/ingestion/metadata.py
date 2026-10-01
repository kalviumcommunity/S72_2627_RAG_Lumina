"""Document metadata: validation of what authors submit and extraction of what the file says.

A mismatch between the two (e.g. the form says v4 but the document header says v3) is recorded as
a parse warning so the approver sees it before approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.models.enums import DocType

DOC_CODE_RE = re.compile(r"^[A-Z]{1,5}(?:-[A-Z0-9]{1,6}){1,3}$")

_DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})"
# Labels must start a line ("Version: 2", or a header-table row "| Version | 2 |" once flattened), so
# prose such as "superseded by version 3" or "amends P-ICU-07 version 3" is never read as metadata.
_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "doc_code": re.compile(
        r"^\s*(?:document\s+code|doc(?:ument)?\s+(?:no|number|id)|(?:circular|sop|protocol)\s+(?:no|number)|"
        r"reference)\.?\s*[:\-]\s*([A-Z]{1,5}(?:-[A-Z0-9]{1,6}){1,3})\b",
        re.I | re.M,
    ),
    "version_label": re.compile(r"^\s*version\s*[:\-]?\s*v?(\d+(?:\.\d+)?)\b", re.I | re.M),
    "effective_from": re.compile(r"^\s*effective(?:\s+(?:from|date))?\s*[:\-]?\s*" + _DATE, re.I | re.M),
    "review_due": re.compile(r"^\s*(?:review\s+(?:due|date)|next\s+review)\s*[:\-]?\s*" + _DATE, re.I | re.M),
}
_TABLE_RULE = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|?)+$")


def _flatten_header_tables(text: str) -> str:
    """Markdown table rows become "Label: value" lines ("| Version | 2 |" → "Version: 2")."""
    lines: list[str] = []
    for line in text.splitlines():
        row = line.strip()
        if not (row.startswith("|") and row.endswith("|")):
            lines.append(line)
            continue
        if _TABLE_RULE.match(row):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        lines.append(f"{cells[0]}: {' '.join(cells[1:])}" if len(cells) > 1 else cells[0])
    return "\n".join(lines)


_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}


def parse_loose_date(value: str) -> date | None:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    match = re.match(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", value)
    if match and match.group(2).lower() in _MONTHS:
        try:
            return date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
        except ValueError:
            return None
    return None


@dataclass
class ExtractedMetadata:
    doc_code: str | None = None
    version_label: str | None = None
    effective_from: date | None = None
    review_due: date | None = None
    title: str | None = None


def extract_metadata(text: str) -> ExtractedMetadata:
    head = _flatten_header_tables(text[:4000])
    found = ExtractedMetadata()
    for name, pattern in _FIELD_PATTERNS.items():
        match = pattern.search(head)
        if not match:
            continue
        raw = match.group(1)
        if name in ("effective_from", "review_due"):
            setattr(found, name, parse_loose_date(raw))
        else:
            setattr(found, name, raw.strip())
    title = re.search(r"^#\s+(.+)$", head, re.M)
    if title:
        found.title = title.group(1).strip()
    return found


@dataclass
class MetadataInput:
    doc_code: str
    title: str
    doc_type: DocType
    version_label: str
    effective_from: date
    review_due: date | None = None
    applies_to_all_branches: bool = True
    branch_codes: list[str] = field(default_factory=list)


def validate_metadata(meta: MetadataInput) -> list[str]:
    """Return human-readable validation errors (empty list = valid)."""
    errors: list[str] = []
    if not DOC_CODE_RE.match(meta.doc_code):
        errors.append("Document code must look like P-ICU-07, DG-01 or C-2026-09")
    if not meta.title.strip():
        errors.append("Title is required")
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,40}", meta.version_label):
        errors.append("Version label must be 1-40 characters (letters, digits, '.', '-')")
    if meta.review_due and meta.review_due < meta.effective_from:
        errors.append("Review due date cannot be before the effective date")
    if not meta.applies_to_all_branches and not meta.branch_codes:
        errors.append("Select at least one branch, or mark the document as network-wide")
    return errors


def metadata_mismatch_warnings(submitted: MetadataInput, extracted: ExtractedMetadata) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []

    def warn(field_name: str, found: str, given: str) -> None:
        warnings.append(
            {
                "code": "metadata_mismatch",
                "field": field_name,
                "message": (
                    f"Document text says {field_name.replace('_', ' ')} '{found}' but the upload form says '{given}'"
                ),
            }
        )

    if extracted.doc_code and extracted.doc_code != submitted.doc_code:
        warn("doc_code", extracted.doc_code, submitted.doc_code)
    if extracted.version_label and extracted.version_label.lstrip("v") != submitted.version_label.lstrip("v"):
        warn("version_label", extracted.version_label, submitted.version_label)
    if extracted.effective_from and extracted.effective_from != submitted.effective_from:
        warn("effective_from", extracted.effective_from.isoformat(), submitted.effective_from.isoformat())
    return warnings
