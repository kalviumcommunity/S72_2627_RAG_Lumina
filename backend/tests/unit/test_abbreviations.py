from __future__ import annotations

import pytest

from app.services.retrieval.abbreviations import expand_query


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Enoxaparin OD or BD?", ["once daily", "twice daily"]),
        ("paracetamol TDS", ["three times daily"]),
        ("morphine SOS dose", ["as needed if required"]),
        ("give stat", ["immediately"]),
        ("KCl via IV", ["potassium chloride", "intravenous"]),
        ("Is Tazocin restricted?", ["piperacillin-tazobactam"]),
        ("pip-taz approval", ["piperacillin-tazobactam"]),
        ("pip taz approval", ["piperacillin-tazobactam"]),
        ("MTP pack 2", ["massive transfusion protocol"]),
        ("aptt target", ["activated partial thromboplastin time"]),
    ],
)
def test_expansions(question: str, expected: list[str]) -> None:
    expanded = expand_query(question)
    for phrase in expected:
        assert phrase in expanded.text
    assert expanded.text.startswith(question)  # the original wording is kept


@pytest.mark.parametrize("question", ["blood culture timing", "Im not sure", "an id badge", "Is it good?"])
def test_case_sensitive_terms_do_not_fire_on_ordinary_words(question: str) -> None:
    assert expand_query(question).expansions == []


def test_no_duplicate_expansions() -> None:
    expanded = expand_query("Tazocin (Zosyn) dose")
    assert expanded.text.count("piperacillin-tazobactam") == 1


def test_expansion_already_present_is_skipped() -> None:
    assert expand_query("intravenous IV access").expansions == []


def test_keyword_text_is_an_or_query() -> None:
    kw = expand_query("heparin rate for aPTT above 100").keyword_text
    assert kw.startswith("heparin or rate or for or aptt or above or 100")
