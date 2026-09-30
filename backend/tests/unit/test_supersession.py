"""Effective-version rule and supersession resolution (safety-critical)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models.enums import VersionStatus
from app.services.ingestion.supersession import (
    SupersessionInfo,
    VersionInfo,
    current_version,
    current_versions_by_document,
    detect_references,
    is_active,
    is_superseded,
    section_matches,
)

DOC = uuid.uuid4()
TODAY = date(2026, 9, 30)


def v(status: VersionStatus, effective: date, approved_at: datetime | None = None, doc: uuid.UUID = DOC) -> VersionInfo:
    return VersionInfo(uuid.uuid4(), doc, status, effective, approved_at)


def link(
    *,
    section: str | None = "4.2",
    effective: date = date(2026, 9, 1),
    confirmed: bool = True,
    source_status: VersionStatus = VersionStatus.approved,
    target: uuid.UUID = DOC,
) -> SupersessionInfo:
    return SupersessionInfo(uuid.uuid4(), source_status, target, section, effective, confirmed)


# ---- current version ------------------------------------------------------------------------------


def test_current_is_latest_approved_effective_version() -> None:
    old = v(VersionStatus.approved, date(2024, 1, 1))
    new = v(VersionStatus.approved, date(2025, 11, 1))
    assert current_version([old, new], TODAY) == new


def test_future_effective_version_is_not_current_yet() -> None:
    now = v(VersionStatus.approved, date(2025, 1, 1))
    future = v(VersionStatus.approved, date(2026, 12, 1))
    assert current_version([now, future], TODAY) == now
    assert current_version([now, future], date(2026, 12, 1)) == future


@pytest.mark.parametrize("status", [VersionStatus.draft, VersionStatus.retired, VersionStatus.superseded])
def test_non_approved_versions_are_never_current(status: VersionStatus) -> None:
    approved = v(VersionStatus.approved, date(2024, 1, 1))
    other = v(status, date(2026, 1, 1))
    assert current_version([approved, other], TODAY) == approved
    assert current_version([other], TODAY) is None


def test_tie_on_effective_date_breaks_on_latest_approval() -> None:
    a = v(VersionStatus.approved, date(2026, 1, 1), datetime(2026, 1, 1, tzinfo=UTC))
    b = v(VersionStatus.approved, date(2026, 1, 1), datetime(2026, 2, 1, tzinfo=UTC))
    assert current_version([a, b], TODAY) == b


def test_current_versions_grouped_by_document() -> None:
    other_doc = uuid.uuid4()
    a = v(VersionStatus.approved, date(2025, 1, 1))
    b = v(VersionStatus.approved, date(2025, 1, 1), doc=other_doc)
    result = current_versions_by_document([a, b], TODAY)
    assert result == {DOC: a, other_doc: b}


# ---- section matching -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "path", "expected"),
    [
        ("4.2", "4.2", True),
        ("4.2", "4.2.1", True),
        ("4.2", "4.2#2", True),
        ("4.2", "4.2(a)", True),
        ("4.2", "4.20", False),
        ("4.2", "4.1", False),
        ("4", "4.2", True),
        (None, "7", True),
    ],
)
def test_section_matches(target: str | None, path: str, expected: bool) -> None:
    assert section_matches(target, path) is expected


# ---- superseded chunks ----------------------------------------------------------------------------


def test_confirmed_effective_link_supersedes_section() -> None:
    assert is_superseded(DOC, ["4.2"], [link()], TODAY)
    assert not is_superseded(DOC, ["4.3"], [link()], TODAY)


def test_whole_document_link_supersedes_every_clause() -> None:
    assert is_superseded(DOC, ["1"], [link(section=None)], TODAY)


def test_unconfirmed_link_does_not_supersede() -> None:
    assert not is_superseded(DOC, ["4.2"], [link(confirmed=False)], TODAY)


def test_link_not_yet_effective_does_not_supersede() -> None:
    assert not is_superseded(DOC, ["4.2"], [link(effective=date(2026, 10, 15))], TODAY)


@pytest.mark.parametrize("status", [VersionStatus.draft, VersionStatus.retired])
def test_draft_or_retired_source_never_supersedes(status: VersionStatus) -> None:
    assert not is_active(link(source_status=status), TODAY)
    assert not is_superseded(DOC, ["4.2"], [link(source_status=status)], TODAY)


def test_source_replaced_by_newer_version_still_supersedes() -> None:
    # Conservative (ADR 0003): a circular replaced by a newer version keeps its amendment in force.
    assert is_superseded(DOC, ["4.2"], [link(source_status=VersionStatus.superseded)], TODAY)


def test_merged_chunk_is_superseded_if_any_covered_clause_is() -> None:
    assert is_superseded(DOC, ["4.1", "4.2"], [link()], TODAY)


def test_link_to_another_document_is_ignored() -> None:
    assert not is_superseded(DOC, ["4.2"], [link(target=uuid.uuid4())], TODAY)


# ---- reference detection --------------------------------------------------------------------------


def test_detects_amendment_with_section() -> None:
    text = "In partial modification of P-ICU-07 §4.2 (Heparin Infusion Protocol), the nomogram is replaced."
    found = detect_references(text, ["P-ICU-07", "DG-02"], "C-2026-09")
    assert [(s.target_doc_code, s.target_section_path) for s in found] == [("P-ICU-07", "4.2")]


def test_detects_section_written_before_the_code() -> None:
    text = "Section 5.3 of P-ED-01 (Sepsis Bundle, version 2) is replaced with effect from 15 September 2026."
    found = detect_references(text, ["P-ED-01"], "C-2026-11")
    assert [(s.target_doc_code, s.target_section_path) for s in found] == [("P-ED-01", "5.3")]


def test_detects_multiple_sections() -> None:
    found = detect_references("| Amends | DG-01 §3.1 and §3.2 |", ["DG-01"], "C-2026-14")
    assert sorted(s.target_section_path or "" for s in found) == ["3.1", "3.2"]


def test_header_table_evidence_is_the_matching_row_only() -> None:
    header = (
        "| Field | Value |\n|:---|---:|\n| Circular number | C-2026-14 |\n"
        "| Amends | DG-01 §3.1 |\n| Issued by | Antimicrobial Stewardship Committee |\n"
    )
    found = detect_references(header, ["DG-01"], "C-2026-14")
    assert [(s.target_section_path, s.evidence) for s in found] == [("3.1", "Amends: DG-01 §3.1")]


def test_bare_citation_without_trigger_word_is_ignored() -> None:
    assert detect_references("Heparin is a high-alert medication (see DG-02).", ["DG-02"], "P-ICU-07") == []


def test_unknown_codes_and_self_references_are_ignored() -> None:
    text = "This circular amends X-999-99 §1 and replaces C-2026-09 §2."
    assert detect_references(text, ["P-ICU-07", "C-2026-09"], "C-2026-09") == []


def test_whole_document_supersession_when_no_section_given() -> None:
    found = detect_references("This protocol supersedes P-ED-01 in full.", ["P-ED-01"], "P-ED-02")
    assert [(s.target_doc_code, s.target_section_path) for s in found] == [("P-ED-01", None)]
